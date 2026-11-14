"""Run in a fresh base-only environment; never hide or uninstall dependencies."""
import importlib.metadata
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

from helseark.adapters.pdf import extract_pdf
from helseark.contracts import ArchiveError, IntakeLimits


def main():
    assert importlib.util.find_spec('pypdf') is None, 'base environment contains pypdf'
    try:
        importlib.metadata.version('pypdf')
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError('base environment contains pypdf metadata')
    with TemporaryDirectory() as root:
        destination = Path(root) / 'out'
        try:
            extract_pdf(Path(__file__).parent / 'fixtures/synthetic/lab-text.pdf',
                        destination, IntakeLimits())
        except ArchiveError as error:
            assert error.code == 'PDF_DEPENDENCY_UNSUPPORTED'
            assert error.details == {'exitCode': 6}
        else:
            raise AssertionError('missing optional dependency accepted')
        assert not destination.exists()
        assert list(Path(root).iterdir()) == []
    print('Base-only import and typed unsupported invocation passed; pypdf absent.')


if __name__ == '__main__':
    main()
