"""fastText reads lower-cased text; text without letters has no language."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from ai_extract.services import language_service


class LanguageTests(SimpleTestCase):
    def test_capital_heading_is_lower_cased_and_spaces_joined(self):
        model = Mock(predict=Mock(return_value=(['__label__vi'], [.99])))
        with patch.object(language_service, '_load', return_value=model):
            self.assertEqual(language_service.language('HỢP ĐỒNG\n  DỊCH VỤ'), 'vi')
        model.predict.assert_called_once_with('hợp đồng dịch vụ', k=1)

    def test_numbers_alone_have_no_language(self):
        with patch.object(language_service, '_load') as load:
            for text in ('30.000.000', '', None, '12/2025 - 03'):
                self.assertIsNone(language_service.language(text))
        load.assert_not_called()
