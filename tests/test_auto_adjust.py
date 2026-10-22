import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from utils.auto_adjust import auto_adjust
from utils.img_adjust import process_image_with_report


class AutoAdjustTests(unittest.TestCase):
    def test_normal_is_exactly_manual_neutral_pipeline(self):
        image = np.full((80, 120, 3), 150, np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'in.png'
            a, b = Path(directory) / 'a.png', Path(directory) / 'b.png'
            cv2.imwrite(str(source), image)
            report = process_image_with_report(str(source), str(a), mode='auto', gamma=3, use_clahe=True)
            process_image_with_report(str(source), str(b), mode='manual')
            self.assertEqual(report['category'], 'neutral')
            np.testing.assert_array_equal(cv2.imread(str(a)), cv2.imread(str(b)))

    def test_dark_image_brightens_but_preserves_shape_and_highlights(self):
        image = np.full((200, 300, 3), 65, np.uint8)
        image[:15, :15] = 255
        result, report = auto_adjust(image)
        self.assertEqual(report['category'], 'dark')
        self.assertEqual(result.shape, image.shape)
        self.assertGreater(float(result[50:150].mean()), 65)
        self.assertLessEqual(report['applied_adjustment']['max_lift'], 18)
        self.assertLessEqual(report['applied_adjustment']['max_drop'], 6)
        np.testing.assert_array_equal(result[:15, :15], image[:15, :15])
        before = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)[:, :, 0].astype(float)
        after = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)[:, :, 0].astype(float)
        self.assertLessEqual(float((after - before).max()), 19)  # includes uint8 color conversion rounding

    def test_uneven_only_lifts_dark_regions(self):
        image = np.full((200, 400, 3), 190, np.uint8)
        image[:, :200] = 65
        for y in range(10, 195, 18):
            image[y:y + 4, 20:180] = 105
        result, report = auto_adjust(image)
        self.assertIn(report['category'], ('uneven', 'mixed'))
        self.assertGreater(float(result[:, :100].mean()), 65)
        self.assertLessEqual(float(np.abs(result[:, 300:].astype(float) - image[:, 300:]).mean()), 1)

    def test_low_contrast_text_gains_contrast_without_sharpening(self):
        image = np.full((240, 400, 3), 155, np.uint8)
        for y in range(18, 230, 22):
            cv2.putText(image, 'PACK 123456', (30, y), cv2.FONT_HERSHEY_SIMPLEX, .7, (110, 110, 110), 2)
        result, report = auto_adjust(image)
        self.assertGreater(report['region_summary']['contrast_cells'], 0)
        region = np.s_[40:200, 40:300]
        before = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)[:, :, 0][region]
        after = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)[:, :, 0][region]
        self.assertGreater(float(np.percentile(after, 90) - np.percentile(after, 10)),
                           float(np.percentile(before, 90) - np.percentile(before, 10)))
        self.assertFalse(report['selected_params']['use_clahe'])

    def test_colored_highlights_match_neutral_before_jpeg(self):
        image = np.full((240, 400, 3), 65, np.uint8)
        image[40:70, 40:100] = (230, 255, 255)
        image[100:130, 180:230] = (255, 250, 240)
        result, report = auto_adjust(image)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        neutral = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        high = lab[:, :, 0] >= 235
        self.assertTrue(high.any())
        np.testing.assert_array_equal(result[high], neutral[high])
        self.assertLessEqual(report['applied_adjustment']['max_lift'], 18)

    def test_noise_alone_does_not_trigger_local_enhancement(self):
        rng = np.random.default_rng(5)
        gray = np.clip(rng.normal(150, 15, (240, 320)), 0, 255).astype(np.uint8)
        image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        _, report = auto_adjust(image)
        self.assertEqual(report['category'], 'neutral')

    def test_small_and_extreme_images(self):
        for value in (0, 255):
            result, report = auto_adjust(np.full((4, 4, 3), value, np.uint8))
            self.assertEqual(result.dtype, np.uint8)
            self.assertTrue(np.isfinite(list(report['metrics'].values())).all())
        with self.assertRaises(ValueError):
            auto_adjust(np.zeros((1, 2, 3), np.uint8))

    def test_upload_and_modes_without_minio(self):
        from app import create_app
        from services.img_adjust_service import ImageAdjustService
        service = ImageAdjustService.__new__(ImageAdjustService)
        image = np.full((60, 80, 3), 65, np.uint8)
        encoded = cv2.imencode('.png', image)[1].tobytes()
        client = create_app('default').test_client()
        with patch('api.img_adjust._get_img_service', return_value=service):
            response = client.post('/api/img-adjust/upload', data={
                'file': (io.BytesIO(encoded), '柜台.png'), 'mode': 'auto', 'gamma': 'invalid-ignored'})
            self.assertEqual(response.status_code, 200)
            data = response.get_json()['data']
            self.assertEqual(data['processing']['category'], 'dark')
            self.assertTrue(data['image_base64'])
            invalid = client.post('/api/img-adjust/upload', data={
                'file': (io.BytesIO(encoded), '柜台.png'), 'mode': 'unknown'})
            self.assertEqual(invalid.status_code, 400)
        self.assertEqual(service._build_params({})['mode'], 'manual')


if __name__ == '__main__':
    unittest.main()
