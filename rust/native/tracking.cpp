#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/video/tracking.hpp>
#include <opencv2/calib3d.hpp>
#include <cmath>

extern "C" void qc_cv_threads(int threads) { cv::setNumThreads(threads); }

// All coordinates are display pixels, top-left origin. No image crosses the FFI owning boundary.
extern "C" int qc_track(const unsigned char *previous, const unsigned char *current,
                        int width, int height, const float *quad, int perspective, float *result) {
    try {
        cv::Mat a(height, width, CV_8UC1, const_cast<unsigned char *>(previous));
        cv::Mat b(height, width, CV_8UC1, const_cast<unsigned char *>(current));
        cv::Mat mask = cv::Mat::zeros(height, width, CV_8UC1);
        std::vector<cv::Point2f> corners;
        for (int i=0; i<4; ++i) corners.emplace_back(quad[2*i], quad[2*i+1]);
        auto roi = cv::boundingRect(corners);
        // Surrounding planar texture makes projective estimation better conditioned than a narrow URL.
        int margin = perspective ? 24 : 10;
        roi = cv::Rect(roi.x-margin, roi.y-margin, roi.width+2*margin, roi.height+2*margin)
            & cv::Rect(0,0,width,height);
        if (roi.empty()) return 0;
        mask(roi).setTo(255);
        std::vector<cv::Point2f> points, moved, back, good_a, good_b;
        cv::goodFeaturesToTrack(a, points, 100, .01, 3, mask);
        int minimum = perspective ? 8 : 4;
        if ((int)points.size() < minimum) return 0;
        std::vector<unsigned char> valid, back_valid;
        std::vector<float> error, back_error;
        cv::TermCriteria criteria(cv::TermCriteria::COUNT|cv::TermCriteria::EPS,40,.01);
        cv::calcOpticalFlowPyrLK(a,b,points,moved,valid,error,cv::Size(25,25),3,criteria);
        cv::calcOpticalFlowPyrLK(b,a,moved,back,back_valid,back_error,cv::Size(25,25),3,criteria);
        for (size_t i=0; i<points.size(); ++i)
            if (valid[i] && back_valid[i] && cv::norm(points[i]-back[i]) < 1.5)
                { good_a.push_back(points[i]); good_b.push_back(moved[i]); }
        if ((int)good_a.size() < minimum) return 0;
        cv::Mat inliers, matrix;
        if (perspective) {
            matrix = cv::findHomography(good_a, good_b, cv::RANSAC, 1.0, inliers, 2000, .995);
            if (matrix.empty() || cv::countNonZero(inliers) < minimum ||
                cv::countNonZero(inliers) < (int)(good_a.size()*.6)) return 0;
            cv::perspectiveTransform(corners, corners, matrix);
        } else {
            matrix = cv::estimateAffinePartial2D(good_a, good_b, inliers, cv::RANSAC, 2.0);
            if (matrix.empty() || cv::countNonZero(inliers) < minimum) return 0;
            cv::transform(corners,corners,matrix);
        }
        for (int i=0;i<4;++i) {
            if (!std::isfinite(corners[i].x) || !std::isfinite(corners[i].y)) return 0;
            result[2*i]=corners[i].x; result[2*i+1]=corners[i].y;
        }
        return 1;
    } catch (const cv::Exception &) { return -1; }
}

// Synthetic projective motion test generator uses the same established warp library.
extern "C" int qc_test_warp(const unsigned char *input, unsigned char *output, int w, int h,
                            const double *matrix) {
    try {
        cv::Mat a(h,w,CV_8UC1,const_cast<unsigned char *>(input)), b(h,w,CV_8UC1,output);
        cv::Mat m(3,3,CV_64F,const_cast<double *>(matrix));
        cv::warpPerspective(a,b,m,cv::Size(w,h));
        return 1;
    } catch (const cv::Exception &) { return 0; }
}

extern "C" void qc_test_texture(unsigned char *output, int w, int h) {
    cv::Mat noise(h,w,CV_8UC1), result(h,w,CV_8UC1,output);
    cv::RNG random(123);random.fill(noise,cv::RNG::UNIFORM,0,255);
    cv::GaussianBlur(noise,result,cv::Size(5,5),1.2);
}
