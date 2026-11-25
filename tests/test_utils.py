import os
import pathlib
import unittest
import tempfile
from unittest import mock

from webvtt.utils import (
    FileWrapper,
    CODEC_BOMS,
    iter_blocks_of_lines,
    _iter_numbered_blocks,
    _split_lines,
    _write_text_file
    )

from .helpers import named_temporary_file


class TestUtils(unittest.TestCase):

    def test_open_file(self):
        with named_temporary_file('w') as f:
            f.write('Hello test!')
            f.flush()
            with FileWrapper.open(f.name) as fw:
                self.assertEqual(fw.file.read(), 'Hello test!')
                self.assertEqual(fw.file.encoding, 'utf-8')

    def test_open_file_with_bom(self):
        for encoding, bom in CODEC_BOMS.items():
            with named_temporary_file('wb') as f:
                f.write(bom)
                f.write('Hello test'.encode(encoding))
                f.flush()

                with FileWrapper.open(f.name) as fw:
                    self.assertEqual(fw.file.read(), 'Hello test')
                    self.assertEqual(fw.file.encoding, encoding)

    def test_atomic_write_keeps_existing_file_if_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'captions.vtt'
            path.write_bytes(b'old')
            with mock.patch('webvtt.utils.os.replace',
                            side_effect=OSError('replace failed')) as replace:
                with self.assertRaisesRegex(OSError, 'replace failed'):
                    _write_text_file(path, 'new', 'utf-8')

            candidate, target = map(pathlib.Path, replace.call_args.args)
            self.assertEqual(target, path.resolve())
            self.assertFalse(candidate.exists())
            self.assertEqual(path.read_bytes(), b'old')
            self.assertEqual(list(path.parent.iterdir()), [path])

    @unittest.skipUnless(os.name == 'posix', 'POSIX modes and links')
    def test_atomic_write_preserves_symlink_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'captions.vtt'
            target.write_bytes(b'old')
            target.chmod(0o640)
            link = target.with_name('subtitles.vtt')
            link.symlink_to(target.name)

            _write_text_file(link, 'new', 'utf-8')

            self.assertTrue(link.is_symlink())
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            self.assertEqual(link.read_bytes(), b'new')

    @unittest.skipUnless(os.name == 'posix', 'POSIX hard links')
    def test_atomic_write_updates_existing_hard_links(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'captions.vtt'
            target.write_bytes(b'old')
            link = target.with_name('subtitles.vtt')
            os.link(target, link)

            _write_text_file(target, 'new', 'utf-8')

            self.assertEqual(link.read_bytes(), b'new')

    def test_write_text_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / 'captions.vtt'
            path.write_text('old')

            _write_text_file(str(path), 'WEBVTT\n\nCafé\n', 'utf-8')

            self.assertEqual(
                path.read_bytes(),
                f'WEBVTT{os.linesep}{os.linesep}Café{os.linesep}'.encode()
                )

    def test_write_text_file_default_encoding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / 'captions.vtt'

            with mock.patch('locale.getpreferredencoding',
                            return_value='utf-16-le'):
                _write_text_file(str(path), 'Café')

            self.assertEqual(path.read_bytes(), 'Café'.encode('utf-16-le'))

    def test_write_text_file_encoding_error_keeps_file(self):
        for encoding, error in (('ascii', UnicodeEncodeError),
                                ('no-such-encoding', LookupError),
                                ('', LookupError)):
            with self.subTest(encoding=encoding):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = pathlib.Path(temp_dir) / 'captions.vtt'
                    path.write_text('old')

                    with self.assertRaises(error):
                        _write_text_file(str(path), 'Café', encoding)

                    self.assertEqual(path.read_text(), 'old')

    def test_iter_blocks_of_lines(self):
        self.assertListEqual(
            list(iter_blocks_of_lines(
                ['', 'block 1', 'line 2', ' ', '', 'block 2', '']
                )),
            [['block 1', 'line 2'], ['block 2']]
            )

    def test_iter_numbered_blocks(self):
        for lines, blocks in (
                ([], []),
                (['', ' '], []),
                (['block'], [(1, ['block'])]),
                (['block', ''], [(1, ['block'])]),
                (['', '', 'a', 'b', ' ', '', 'c', 'd'],
                 [(3, ['a', 'b']), (7, ['c', 'd'])]),
                ):
            with self.subTest(lines=lines):
                self.assertListEqual(
                    list(_iter_numbered_blocks(lines)),
                    blocks
                    )

    def test_split_lines(self):
        for text in ('',
                     '\n',
                     'line 1',
                     'line 1\n',
                     'line 1\r\nline 2\rline 3\nline 4',
                     'line 1\n\nline 2\r\n',
                     'line 1\r\r\n',
                     ):
            with self.subTest(text=text):
                self.assertListEqual(_split_lines(text), text.splitlines())

    def test_split_lines_only_on_cr_and_lf(self):
        self.assertListEqual(
            _split_lines('a\x0bb\x0cc\x1cd\x1de\x1ef\x85g\u2028h\u2029i\nj'),
            ['a\x0bb\x0cc\x1cd\x1de\x1ef\x85g\u2028h\u2029i', 'j']
            )
