from django.contrib.staticfiles.finders import FileSystemFinder


class FrontendFinder(FileSystemFinder):
    """frontend/<topic>/ keeps each page's template beside its css/js; only the css/js are served as static files."""

    def find(self, path, **kwargs):
        if path.endswith('.html'):
            return [] if kwargs.get('all') or kwargs.get('find_all') else None
        return super().find(path, **kwargs)

    def list(self, ignore_patterns):
        return super().list([*(ignore_patterns or []), '*.html'])
