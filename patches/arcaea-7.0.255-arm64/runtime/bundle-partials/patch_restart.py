"""Pinned release additions; preserve HTTP guards inside a cancellation-safe body scope."""
import re
CALLER = 'org/cocos2dx/lib/Cocos2dxDownloader$3.smali'
HANDLER = 'org/cocos2dx/lib/FileTaskHandler.smali'
HELPER = 'org/cocos2dx/lib/AkaineBundlePartialCache.smali'
SELECT = '''    iget-object v3, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$url:Ljava/lang/String;

    invoke-static {v1, v3, v2}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->select(Ljava/io/File;Ljava/lang/String;Ljava/io/File;)Ljava/io/File;

    move-result-object v1

'''
RELEASE = '''    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->finished(Lorg/cocos2dx/lib/FileTaskHandler;)V

'''
FIELDS = '''.field _akaineCacheCancelled:Z

.field _akaineCacheWriting:Z

.field _akaineCacheReleased:Z

'''
CANCEL = '''.method public onCancel()V
    .registers 1

    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->cancelled(Lorg/cocos2dx/lib/FileTaskHandler;)V

    invoke-super {p0}, Lcom/loopj/android/http/FileAsyncHttpResponseHandler;->onCancel()V

    return-void
.end method

'''
BEGIN = '''    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->begin(Lorg/cocos2dx/lib/FileTaskHandler;)V

    :akaine_cache_body_start
'''
END = '''    :akaine_cache_body_end
    .catchall {:akaine_cache_body_start .. :akaine_cache_body_end} :akaine_cache_body_failed

    :akaine_cache_body_done
    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->end(Lorg/cocos2dx/lib/FileTaskHandler;)V

    return-void

    :akaine_cache_body_failed
    move-exception v0

    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->end(Lorg/cocos2dx/lib/FileTaskHandler;)V

    throw v0
'''
METHOD = re.compile(r'(?ms)^\.method public sendResponseMessage\(Lcz/msebera/android/httpclient/HttpResponse;\)V\n.*?^\.end method$')


def unwrap(handler):
    value = handler.replace(RELEASE, '').replace(FAILURE, '').replace(FIELDS, '').replace(CANCEL, '')
    value = value.replace(BEGIN, '').replace(END, '').replace('    goto :akaine_cache_body_done', '    return-void')
    return value
FAILURE = '''    invoke-virtual {p0}, Lorg/cocos2dx/lib/FileTaskHandler;->getTargetFile()Ljava/io/File;

    move-result-object v0

    invoke-static {p1, v0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->failed(ILjava/io/File;)V

'''


def patch(caller, handler):
    site = '    new-instance v3, Lorg/cocos2dx/lib/FileTaskHandler;'
    assert caller.count(site) == 1 and 'AkaineBundlePartialCache' not in caller
    changed_caller = caller.replace(site, SELECT + site)
    site = '.method public onFinish()V\n    .registers 2\n\n'
    assert handler.count(site) == 1 and 'AkaineBundlePartialCache' not in handler
    changed_handler = handler.replace(site, site + RELEASE)
    site = '.method public onFailure(I[Lcz/msebera/android/httpclient/Header;Ljava/lang/Throwable;Ljava/io/File;)V\n    .registers 7\n\n'
    assert changed_handler.count(site) == 1
    changed_handler = changed_handler.replace(site, site + FAILURE)
    changed_handler = changed_handler.replace('# instance fields\n', '# instance fields\n' + FIELDS)
    changed_handler = changed_handler.replace('# virtual methods\n', '# virtual methods\n' + CANCEL)
    match = METHOD.search(changed_handler)
    assert match and match.group().count('    return-void') == 1
    body = match.group()
    site = '    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;'
    assert body.count(site) == 1
    body = body.replace(site, BEGIN + site).replace('    return-void', '    goto :akaine_cache_body_done')
    body = body.replace('.end method', END + '.end method')
    changed_handler = changed_handler[:match.start()] + body + changed_handler[match.end():]
    assert changed_caller.replace(SELECT, '') == caller
    assert unwrap(changed_handler) == handler
    return changed_caller, changed_handler
