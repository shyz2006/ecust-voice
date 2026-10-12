"""OpenAI兼容客户端全引擎用量钩子；只保存usage与状态，不记录请求/密钥。"""
import inspect
import time
from loguru import logger


def _engine():
    frame = inspect.currentframe()
    try:
        while frame:
            name=frame.f_globals.get('__name__','')
            for engine in ('CampusPulse','QueryEngine','InsightEngine','MediaEngine','ReportEngine','ForumEngine','MindSpider'):
                if name==engine or name.startswith(engine+'.'):
                    return engine
            frame=frame.f_back
        return '其他模型调用'
    finally:
        del frame


def _record(usage,seconds,success,engine):
    try:
        from CampusPulse.telemetry import record_response
        record_response(usage,seconds,success,engine)
    except Exception:
        # 台账故障不重发已经成功的付费请求；只记不含参数的告警。
        logger.warning('[用量台账] 写入失败，本次用量未能保存')


class UsageStream:
    def __init__(self,stream,started,engine):
        self.stream=stream;self.started=started;self.engine=engine
        self.usage=None;self.recorded=False;self.complete=False
    def _save(self,success):
        if not self.recorded:
            self.recorded=True
            _record(self.usage,time.monotonic()-self.started,success,self.engine)
    def __iter__(self):
        try:
            for chunk in self.stream:
                usage=getattr(chunk,'usage',None)
                if usage is not None:self.usage=usage
                # 正常结束标志；服务商的usage可能在后续空choices块中返回。
                if any(getattr(c,'finish_reason',None) is not None for c in (getattr(chunk,'choices',None) or [])):
                    self.complete=True
                yield chunk
        except BaseException:
            self._save(False)
            raise
        else:
            self._save(self.complete)
    def close(self):
        try:return self.stream.close()
        finally:self._save(self.complete)
    def __enter__(self):
        if hasattr(self.stream,'__enter__'):self.stream.__enter__()
        return self
    def __exit__(self,*exc):
        try:
            if hasattr(self.stream,'__exit__'):return self.stream.__exit__(*exc)
        finally:self._save(self.complete and exc[0] is None)
    def __getattr__(self,name):return getattr(self.stream,name)


def wrap_create(original):
    def create(self,*args,**kwargs):
        started=time.monotonic();engine=_engine()
        streaming=bool(kwargs.get('stream'))
        # 标准流式usage。若兼容网关明确拒绝此参数，仅移除该参数后重试一次。
        added=streaming and 'stream_options' not in kwargs
        if added:kwargs['stream_options']={'include_usage':True}
        try:
            try:response=original(self,*args,**kwargs)
            except Exception as exc:
                text=str(exc).lower()
                if added and getattr(exc,'status_code',None)==400 and ('stream_options' in text or 'include_usage' in text):
                    _record(None,time.monotonic()-started,False,engine)
                    kwargs.pop('stream_options',None)
                    started=time.monotonic()
                    response=original(self,*args,**kwargs)
                else:raise
        except Exception:
            _record(None,time.monotonic()-started,False,engine)
            raise
        if streaming:return UsageStream(response,started,engine)
        _record(getattr(response,'usage',None),time.monotonic()-started,True,engine)
        return response
    create._bf_usage_ledger=True
    create._bf_cache_key=getattr(original,'_bf_cache_key',False)
    return create


def install():
    try:
        from openai.resources.chat.completions import Completions
    except ImportError:
        return
    if not getattr(Completions.create,'_bf_usage_ledger',False):
        Completions.create=wrap_create(Completions.create)
