import importlib, sys, types
from unittest import mock

sys.modules.pop('controls.file_preview', None)
fp = importlib.import_module('controls.file_preview')
owner = types.SimpleNamespace(
    current_preview_path='sample.docx',
    preview_load_all_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_rotate_menu_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_import_from_file_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_export_pages_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_move_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_remove_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_adjust_page_width_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
    preview_optimize_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
)
with mock.patch.object(fp, 'is_pdf_file', return_value=False), \
     mock.patch.object(fp.office_preview, 'can_preview_office', return_value=True), \
     mock.patch.object(fp.office_preview, 'get_office_document_page_count', return_value=3), \
     mock.patch.object(fp.pdf_utils, '_get_show_pages_limit_for_path', return_value=2):
    print('allowed', fp.is_office_preview_allowed(owner, 'sample.docx'))
    print('page_limit', fp._is_preview_page_limit_active('sample.docx', owner=owner))
    fp.update_load_all_btn_state(owner)
    print('load_all_calls', owner.preview_load_all_btn.Enable.call_args_list)

owner2 = types.SimpleNamespace(current_preview_path='sample.docx', pdf_preview_zoom=1.0, pdf_page_view_mode=fp.PAGE_VIEW_MODE_1_WIDE, busy_cursor=lambda: fp.nullcontext())
with mock.patch.object(fp, '_get_preview_owner_from_event', return_value=owner2), \
     mock.patch.object(fp.office_preview, 'convert_office_to_preview_pdf', return_value='converted.pdf'), \
     mock.patch.object(fp, 'show_pdf_feed') as mocked_show:
    fp.on_preview_zoom_in(types.SimpleNamespace())
    print('zoom', owner2.pdf_preview_zoom, owner2.pdf_page_view_mode)
    print('show', mocked_show.call_args_list)
