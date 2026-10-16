#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreImage/CoreImage.h>
#import <Vision/Vision.h>
#import <Metal/Metal.h>
#import <VideoToolbox/VideoToolbox.h>
#import <Accelerate/Accelerate.h>
#include <cstdlib>
#include <cstring>
#include <string>

static thread_local std::string lastError;
static int fail(NSString *message) { lastError = message.UTF8String ?: "Native media failure"; return -1; }
extern "C" const char *qc_apple_error() { return lastError.c_str(); }

@interface QCReader : NSObject
@property AVAssetReader *reader;
@property AVAssetReaderTrackOutput *output;
@property CIContext *context;
@property CIImage *image;
@property VNRecognizeTextRequest *request;
@property CGAffineTransform transform;
@property CMSampleBufferRef sample;
@end
@implementation QCReader
- (void)dealloc { if (_sample) CFRelease(_sample); [_reader cancelReading]; }
@end

static CIContext *metalContext() {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device) return nil;
    return [CIContext contextWithMTLDevice:device options:@{kCIContextCacheIntermediates:@NO}];
}
extern "C" int qc_metal_available() { @autoreleasepool { return MTLCreateSystemDefaultDevice()!=nil; } }
extern "C" void *qc_reader_open(const char *path) {
    @autoreleasepool {
        NSError *error=nil;
        AVURLAsset *asset=[AVURLAsset URLAssetWithURL:[NSURL fileURLWithPath:[NSString stringWithUTF8String:path]] options:nil];
        AVAssetTrack *track=[[asset tracksWithMediaType:AVMediaTypeVideo] firstObject];
        if (!track) { fail(@"No video track"); return nullptr; }
        QCReader *r=[QCReader new];
        r.context=metalContext();
        if (!r.context) { fail(@"Metal device unavailable"); return nullptr; }
        r.reader=[[AVAssetReader alloc] initWithAsset:asset error:&error];
        r.output=[[AVAssetReaderTrackOutput alloc] initWithTrack:track outputSettings:@{
            (id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)}];
        r.output.alwaysCopiesSampleData=NO;
        if (![r.reader canAddOutput:r.output]) { fail(@"Unsupported video reader"); return nullptr; }
        [r.reader addOutput:r.output];
        if (![r.reader startReading]) { fail(r.reader.error.localizedDescription); return nullptr; }
        CGAffineTransform t=track.preferredTransform;
        // AV track transforms use top-left image axes; Core Image uses bottom-left axes.
        r.transform=CGAffineTransformMake(t.a,-t.b,-t.c,t.d,0,0);
        r.request=[VNRecognizeTextRequest new];
        r.request.recognitionLevel=VNRequestTextRecognitionLevelAccurate;
        r.request.usesLanguageCorrection=NO;
        r.request.recognitionLanguages=@[@"en-US"];
        r.request.usesCPUOnly=NO;
        r.request.minimumTextHeight=.004;
        return (__bridge_retained void *)r;
    }
}
extern "C" void qc_reader_close(void *handle) { @autoreleasepool { (void)CFBridgingRelease(handle); } }
extern "C" int qc_reader_next(void *handle, unsigned char *gray, int width, int height,
                              int64_t *pts, int32_t *timescale) {
    @autoreleasepool {
        QCReader *r=(__bridge QCReader *)handle;
        if (r.sample) { CFRelease(r.sample); r.sample=nullptr; }
        r.sample=[r.output copyNextSampleBuffer];
        if (!r.sample) {
            if (r.reader.status==AVAssetReaderStatusFailed) return fail(r.reader.error.localizedDescription);
            return 0;
        }
        CMTime time=CMSampleBufferGetPresentationTimeStamp(r.sample);
        *pts=time.value; *timescale=time.timescale;
        CVPixelBufferRef pixels=CMSampleBufferGetImageBuffer(r.sample);
        r.image=[[CIImage imageWithCVPixelBuffer:pixels] imageByApplyingTransform:r.transform];
        CGRect extent=r.image.extent;
        r.image=[r.image imageByApplyingTransform:CGAffineTransformMakeTranslation(-extent.origin.x,-extent.origin.y)];
        if (gray) {
            CIImage *small=[r.image imageByApplyingTransform:CGAffineTransformMakeScale(width/r.image.extent.size.width,height/r.image.extent.size.height)];
            CGColorSpaceRef cs=CGColorSpaceCreateDeviceGray();
            // CGImage byte rows are top-down, matching OpenCV and exported quadrilaterals.
            CGImageRef cg=[r.context createCGImage:small fromRect:CGRectMake(0,0,width,height) format:kCIFormatL8 colorSpace:cs];
            CGColorSpaceRelease(cs);
            if (!cg) return fail(@"Cannot create grayscale tracking frame");
            CFDataRef data=CGDataProviderCopyData(CGImageGetDataProvider(cg));
            const unsigned char *bytes=CFDataGetBytePtr(data);
            size_t row=CGImageGetBytesPerRow(cg);
            for (int y=0;y<height;++y) memcpy(gray+y*width,bytes+y*row,width);
            CFRelease(data); CGImageRelease(cg);
        }
        return 1;
    }
}

static NSArray *quad(VNRectangleObservation *box, double w, double h) {
    if (!box) return nil;
    return @[@[@(box.topLeft.x*w),@((1-box.topLeft.y)*h)],
             @[@(box.topRight.x*w),@((1-box.topRight.y)*h)],
             @[@(box.bottomRight.x*w),@((1-box.bottomRight.y)*h)],
             @[@(box.bottomLeft.x*w),@((1-box.bottomLeft.y)*h)]];
}
extern "C" char *qc_ocr(void *handle, int sideways) {
    @autoreleasepool {
        QCReader *r=(__bridge QCReader *)handle;
        NSMutableArray *lines=[NSMutableArray new];
        for (int turn=0;turn<(sideways?2:1);++turn) {
            CIImage *image=r.image;
            if (turn) {
                image=[image imageByApplyingTransform:CGAffineTransformMakeRotation(M_PI_2)];
                image=[image imageByApplyingTransform:CGAffineTransformMakeTranslation(-image.extent.origin.x,-image.extent.origin.y)];
            }
            VNImageRequestHandler *handler=[[VNImageRequestHandler alloc] initWithCIImage:image options:@{}];
            NSError *error=nil;
            if (![handler performRequests:@[r.request] error:&error]) { fail(error.localizedDescription); return nullptr; }
            for (VNRecognizedTextObservation *observation in r.request.results) {
                VNRecognizedText *text=[[observation topCandidates:1] firstObject];
                if (!text) continue;
                NSMutableArray *chars=[NSMutableArray new];
                for (NSUInteger i=0;i<text.string.length;++i) {
                    VNRectangleObservation *bounds=[text boundingBoxForRange:NSMakeRange(i,1) error:nil];
                    [chars addObject:quad(bounds,image.extent.size.width,image.extent.size.height) ?: (id)[NSNull null]];
                }
                [lines addObject:@{@"text":text.string,@"confidence":@(text.confidence),@"quad":quad(observation,image.extent.size.width,image.extent.size.height),@"chars":chars,@"turn":@(turn)}];
            }
        }
        NSData *json=[NSJSONSerialization dataWithJSONObject:lines options:0 error:nil];
        char *result=(char *)malloc(json.length+1);
        memcpy(result,json.bytes,json.length); result[json.length]=0;
        return result;
    }
}
extern "C" void qc_free_string(char *value) { free(value); }

@interface QCWriter : NSObject
@property AVAssetWriter *writer;
@property AVAssetWriterInput *input;
@property AVAssetWriterInputPixelBufferAdaptor *adaptor;
@property CIContext *context;
@property int width;
@property int height;
@end
@implementation QCWriter
- (void)dealloc { if (_writer.status==AVAssetWriterStatusWriting) [_writer cancelWriting]; }
@end

extern "C" void *qc_writer_open(const char *path, int width, int height, double fps, int bitrate) {
    @autoreleasepool {
        NSError *error=nil;
        QCWriter *w=[QCWriter new];
        w.context=metalContext(); w.width=width;w.height=height;
        w.writer=[[AVAssetWriter alloc] initWithURL:[NSURL fileURLWithPath:[NSString stringWithUTF8String:path]] fileType:AVFileTypeMPEG4 error:&error];
        if (!w.writer) { fail(error.localizedDescription); return nullptr; }
        NSDictionary *settings=@{AVVideoCodecKey:AVVideoCodecTypeH264, AVVideoWidthKey:@(width), AVVideoHeightKey:@(height),
            AVVideoEncoderSpecificationKey:@{(id)kVTVideoEncoderSpecification_EnableHardwareAcceleratedVideoEncoder:@YES,
                                            (id)kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder:@YES},
            AVVideoColorPropertiesKey:@{AVVideoColorPrimariesKey:AVVideoColorPrimaries_ITU_R_709_2,AVVideoTransferFunctionKey:AVVideoTransferFunction_ITU_R_709_2,AVVideoYCbCrMatrixKey:AVVideoYCbCrMatrix_ITU_R_709_2},
            AVVideoCompressionPropertiesKey:@{AVVideoAverageBitRateKey:@(bitrate),AVVideoExpectedSourceFrameRateKey:@(fps),AVVideoAllowFrameReorderingKey:@NO}};
        w.input=[[AVAssetWriterInput alloc] initWithMediaType:AVMediaTypeVideo outputSettings:settings];
        w.input.mediaTimeScale=720000;
        w.writer.movieTimeScale=720000;
        w.input.expectsMediaDataInRealTime=NO;
        w.adaptor=[[AVAssetWriterInputPixelBufferAdaptor alloc] initWithAssetWriterInput:w.input sourcePixelBufferAttributes:@{
            (id)kCVPixelBufferPixelFormatTypeKey:@(kCVPixelFormatType_32BGRA), (id)kCVPixelBufferWidthKey:@(width),
            (id)kCVPixelBufferHeightKey:@(height), (id)kCVPixelBufferMetalCompatibilityKey:@YES, (id)kCVPixelBufferIOSurfacePropertiesKey:@{}}];
        if (![w.writer canAddInput:w.input]) { fail(@"Unsupported hardware video encoder");return nullptr; }
        [w.writer addInput:w.input];
        if (![w.writer startWriting]) { fail(w.writer.error.localizedDescription);return nullptr; }
        [w.writer startSessionAtSourceTime:kCMTimeZero];
        return (__bridge_retained void *)w;
    }
}
extern "C" void qc_writer_close(void *handle) { @autoreleasepool { (void)CFBridgingRelease(handle); } }
extern "C" int qc_writer_frame(void *writer, void *reader, const double *quads, int count,
                               double sigma, double feather, int64_t pts, int32_t timescale) {
    @autoreleasepool {
        QCWriter *w=(__bridge QCWriter *)writer;
        QCReader *r=(__bridge QCReader *)reader;
        CGRect extent=CGRectMake(0,0,w.width,w.height);
        CIImage *image=r.image;
        if (count) {
            CIImage *mask=[[CIImage imageWithColor:[CIColor colorWithRed:0 green:0 blue:0 alpha:1]] imageByCroppingToRect:extent];
            CIImage *white=[[CIImage imageWithColor:[CIColor colorWithRed:1 green:1 blue:1 alpha:1]] imageByCroppingToRect:extent];
            for (int i=0;i<count;++i) {
                const double *p=quads+i*8;
                NSDictionary *corners=@{@"inputTopLeft":[CIVector vectorWithX:p[0] Y:w.height-p[1]],
                    @"inputTopRight":[CIVector vectorWithX:p[2] Y:w.height-p[3]],
                    @"inputBottomRight":[CIVector vectorWithX:p[4] Y:w.height-p[5]],
                    @"inputBottomLeft":[CIVector vectorWithX:p[6] Y:w.height-p[7]]};
                CIImage *shape=[white imageByApplyingFilter:@"CIPerspectiveTransform" withInputParameters:corners];
                mask=[shape imageByApplyingFilter:@"CIMaximumCompositing" withInputParameters:@{kCIInputBackgroundImageKey:mask}];
            }
            if (feather>0) mask=[mask imageByApplyingFilter:@"CIGaussianBlur" withInputParameters:@{kCIInputRadiusKey:@(feather)}];
            CIImage *blurred=[[image imageByClampingToExtent] imageByApplyingFilter:@"CIGaussianBlur" withInputParameters:@{kCIInputRadiusKey:@(sigma)}];
            image=[blurred imageByApplyingFilter:@"CIBlendWithMask" withInputParameters:@{kCIInputBackgroundImageKey:image,kCIInputMaskImageKey:mask}];
        }
        CFAbsoluteTime deadline=CFAbsoluteTimeGetCurrent()+30;
        while (!w.input.readyForMoreMediaData && w.writer.status==AVAssetWriterStatusWriting && CFAbsoluteTimeGetCurrent()<deadline) [NSThread sleepForTimeInterval:.001];
        if (!w.input.readyForMoreMediaData) return fail(w.writer.error.localizedDescription ?: @"Hardware writer stalled");
        CVPixelBufferRef buffer=nullptr;
        if (CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault,w.adaptor.pixelBufferPool,&buffer)!=kCVReturnSuccess) return fail(@"Pixel buffer allocation failed");
        CGColorSpaceRef space=CGColorSpaceCreateWithName(kCGColorSpaceITUR_709);
        [w.context render:image toCVPixelBuffer:buffer bounds:extent colorSpace:space];
        CGColorSpaceRelease(space);
        BOOL ok=[w.adaptor appendPixelBuffer:buffer withPresentationTime:CMTimeMake(pts,timescale)];
        CVPixelBufferRelease(buffer);
        if (!ok) return fail(w.writer.error.localizedDescription ?: @"Video append failed");
        return 1;
    }
}
extern "C" int qc_writer_finish(void *handle, double duration) {
    @autoreleasepool {
        QCWriter *w=(__bridge QCWriter *)handle;
        [w.writer endSessionAtSourceTime:CMTimeMakeWithSeconds(duration,720000)];
        [w.input markAsFinished];
        dispatch_semaphore_t done=dispatch_semaphore_create(0);
        [w.writer finishWritingWithCompletionHandler:^{dispatch_semaphore_signal(done);}];
        if (dispatch_semaphore_wait(done,dispatch_time(DISPATCH_TIME_NOW,30*NSEC_PER_SEC))) return fail(@"Writer finalization timed out");
        if (w.writer.status!=AVAssetWriterStatusCompleted) return fail(w.writer.error.localizedDescription);
        return 1;
    }
}
