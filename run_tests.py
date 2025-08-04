import os
import sys
import unittest
import logging


def run_tests() -> bool:
    """Discover and run tests, returning True if all pass."""
    loader = unittest.TestLoader()
    suite = loader.discover('tests')

    github_mode = os.getenv('GITHUB_ACTIONS', 'false').lower() == 'true'

    if github_mode:
        try:
            import xmlrunner  # type: ignore
            os.makedirs('test-results', exist_ok=True)
            output_path = os.path.join('test-results', 'unittest.xml')
            with open(output_path, 'wb') as output:
                runner = xmlrunner.XMLTestRunner(output=output)
                logging.info('[runner] Running in GitHub Actions mode - XML output will be saved to %s', output_path)
                result = runner.run(suite)
        except ImportError:
            logging.warning('[runner] Warning: unittest-xml-reporting not installed. Falling back to default runner.')
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
    else:
        logging.info('[runner] Running in local mode - Console output only.')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

    return result.wasSuccessful()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    try:
        success = run_tests()
    except Exception:
        logging.exception('Test run failed due to an unexpected error.')
        return 1
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
