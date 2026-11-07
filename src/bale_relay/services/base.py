class Service:
    def __init__(self, ctx):
        self.ctx = ctx
    @property
    def config(self): return self.ctx.config
    @property
    def http(self): return self.ctx.http
    @property
    def cache(self): return self.ctx.cache
