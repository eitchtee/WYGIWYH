import logging


class ProcrastinateFilter(logging.Filter):
    # from https://github.com/madzak/python-json-logger/blob/master/src/pythonjsonlogger/jsonlogger.py#L19
    _reserved_log_keys = frozenset(
        """args asctime created exc_info exc_text filename
        funcName levelname levelno lineno module msecs message msg name pathname
        process processName relativeCreated stack_info thread threadName""".split()
    )

    def filter(self, record: logging.LogRecord):
        record.procrastinate = {}
        for key, value in vars(record).items():
            if not key.startswith("_") and key not in self._reserved_log_keys | {
                "procrastinate"
            }:
                record.procrastinate[key] = value  # type: ignore
        return True
