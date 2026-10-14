# Collector dependency recovery

After the 2,402-page checkpoint, the prior collector process was absent. A restart failed because Python could no longer read `.tools/bs4/__init__.py`; the stderr log reported PermissionError. No archive fetch failure or graceful-stop request was recorded for the prior exit, so its cause remains unconfirmed.

The pinned requirements were installed into a fresh ignored `.tools-current/` directory inside crowdsourced. Installation used no pip cache or bytecode compilation, with temporary installation files directed into `.cache/tool-install/`. The collector prefers the new directory when present and retains compatibility with older `.tools/` installations. Existing dependencies were not deleted or subjected to permission changes.

All 116 tests passed after recovery. The downloader resumed from the existing 102,120-page queue, and four subsequent ability pages were confirmed fetched by the new live process. No prior raw batch or server content was changed.
