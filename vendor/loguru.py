class FakeLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass
    def catch(self, *args, **kwargs): 
        def decorator(func):
            return func
        return decorator

logger = FakeLogger()
