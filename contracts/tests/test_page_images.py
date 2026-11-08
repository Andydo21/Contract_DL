"""Photos of one document, page by page, become one PDF in the order the user sent them."""
import io
from tempfile import TemporaryDirectory

import fitz
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from contracts.services.page_images_service import PageImagesError, images_to_pdf

COLOURS = {'red': (220, 30, 30), 'green': (30, 180, 60), 'blue': (40, 60, 220)}


def photo(name, colour, size=(300, 400), exif_turn=None, kind='JPEG'):
    image = Image.new('RGB', size, COLOURS[colour])
    buffer = io.BytesIO()
    options = {}
    if exif_turn:
        exif = Image.Exif()
        exif[0x0112] = exif_turn
        options['exif'] = exif
    image.save(buffer, kind, **options)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg' if kind == 'JPEG' else 'image/png')


def pages(content):
    document = fitz.open(stream=content.read(), filetype='pdf')
    out = []
    for page in document:
        pixmap = page.get_pixmap(dpi=20)
        r, g, b = pixmap.pixel(pixmap.width//2, pixmap.height//2)
        colour = min(COLOURS, key=lambda name: sum(abs(x-y) for x, y in zip(COLOURS[name], (r, g, b))))
        out.append((colour, page.rect.width < page.rect.height))
    return out


class JoinTests(SimpleTestCase):
    def test_pages_follow_the_order_sent_not_the_file_names(self):
        joined = images_to_pdf([photo('IMG_3.jpg', 'blue'), photo('IMG_1.jpg', 'red'), photo('IMG_2.png', 'green', kind='PNG')])
        self.assertTrue(joined.name.endswith('_3_trang.pdf'))
        self.assertEqual([c for c, _ in pages(joined)], ['blue', 'red', 'green'])

    def test_the_camera_turn_written_in_exif_is_applied(self):
        # Stored 400 wide and 300 tall with EXIF "rotate 90": the page the user saw is portrait.
        joined = images_to_pdf([photo('a.jpg', 'red', size=(400, 300), exif_turn=6), photo('b.jpg', 'green', size=(400, 300))])
        self.assertEqual([portrait for _, portrait in pages(joined)], [True, False])

    def test_a_file_that_is_not_a_photo_or_not_readable_is_refused_with_its_page_number(self):
        for bad in (SimpleUploadedFile('hop-dong.pdf', b'%PDF-1.4'), SimpleUploadedFile('broken.jpg', b'not an image')):
            with self.subTest(name=bad.name), self.assertRaisesRegex(PageImagesError, 'Trang 2'):
                images_to_pdf([photo('a.jpg', 'red'), bad])


@override_settings(MEDIA_ROOT=TemporaryDirectory().name)
class UploadTests(TestCase):
    def setUp(self):
        from contracts.models import Company, Role, User
        role, _ = Role.objects.get_or_create(role_name='MANAGER')
        company = Company.objects.create(company_name='Tenant')
        self.client.force_login(User.objects.create_user('manager_photos', password='x', company=company, role=role))

    def test_several_photos_create_one_contract_with_one_pdf(self):
        from contracts.models import Contract, ContractFile
        response = self.client.post('/api/contracts/', dict(contract_code='P-1', title='Ảnh chụp',
                                    file=[photo('p1.jpg', 'red'), photo('p2.jpg', 'green')]))
        self.assertEqual(response.status_code, 200, response.content)
        files = ContractFile.objects.filter(version__contract=Contract.objects.get(contract_code='P-1'))
        self.assertEqual(files.count(), 1)
        self.assertTrue(files.get().file_path.endswith('_2_trang.pdf'))

    def test_one_file_is_stored_as_it_is_and_mixed_files_are_refused(self):
        from contracts.models import Contract, ContractFile
        self.client.post('/api/contracts/', dict(contract_code='P-2', title='Một ảnh', file=photo('p1.jpg', 'red')))
        self.assertTrue(ContractFile.objects.get(version__contract=Contract.objects.get(contract_code='P-2')).file_path.endswith('p1.jpg'))
        response = self.client.post('/api/contracts/', dict(contract_code='P-3', title='Lẫn',
                                    file=[photo('p1.jpg', 'red'), SimpleUploadedFile('a.pdf', b'%PDF-1.4')]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Trang 2', response.json()['error'])
        self.assertFalse(Contract.objects.filter(contract_code='P-3').exists())
