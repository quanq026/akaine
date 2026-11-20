.method public sendResponseMessage(Lcz/msebera/android/httpclient/HttpResponse;)V
    .locals 5
    .annotation system Ldalvik/annotation/Throws;
        value = {
            Ljava/io/IOException;
        }
    .end annotation

    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;
    move-result-object v0
    invoke-virtual {v0}, Ljava/lang/Thread;->isInterrupted()Z
    move-result v0
    if-nez v0, :delegate_response

    invoke-interface {p1}, Lcz/msebera/android/httpclient/HttpResponse;->getStatusLine()Lcz/msebera/android/httpclient/StatusLine;
    move-result-object v0
    invoke-interface {v0}, Lcz/msebera/android/httpclient/StatusLine;->getStatusCode()I
    move-result v0
    const/16 v1, 0xc8
    if-ne v0, v1, :check_partial_response

    # A full response replaces any partial bytes, including an HTTP client's retry.
    invoke-virtual {p0}, Lorg/cocos2dx/lib/FileTaskHandler;->getTargetFile()Ljava/io/File;
    move-result-object v0
    new-instance v1, Ljava/io/FileOutputStream;
    const/4 v2, 0x0
    invoke-direct {v1, v0, v2}, Ljava/io/FileOutputStream;-><init>(Ljava/io/File;Z)V
    invoke-virtual {v1}, Ljava/io/FileOutputStream;->close()V
    const-wide/16 v0, 0x0
    iput-wide v0, p0, Lorg/cocos2dx/lib/FileTaskHandler;->_initFileLen:J
    iput-wide v0, p0, Lorg/cocos2dx/lib/FileTaskHandler;->_lastBytesWritten:J
    goto :delegate_response

    :check_partial_response
    const/16 v1, 0xce
    if-ne v0, v1, :delegate_response
    const-string v0, "Content-Range"
    invoke-interface {p1, v0}, Lcz/msebera/android/httpclient/HttpResponse;->getFirstHeader(Ljava/lang/String;)Lcz/msebera/android/httpclient/Header;
    move-result-object v0
    if-eqz v0, :invalid_range
    invoke-interface {v0}, Lcz/msebera/android/httpclient/Header;->getValue()Ljava/lang/String;
    move-result-object v0
    if-eqz v0, :invalid_range
    const-string v1, "bytes ([0-9]+)-[0-9]+/(?:[0-9]+|[*])"
    invoke-static {v1}, Ljava/util/regex/Pattern;->compile(Ljava/lang/String;)Ljava/util/regex/Pattern;
    move-result-object v1
    invoke-virtual {v1, v0}, Ljava/util/regex/Pattern;->matcher(Ljava/lang/CharSequence;)Ljava/util/regex/Matcher;
    move-result-object v0
    invoke-virtual {v0}, Ljava/util/regex/Matcher;->matches()Z
    move-result v1
    if-eqz v1, :invalid_range
    const/4 v1, 0x1
    invoke-virtual {v0, v1}, Ljava/util/regex/Matcher;->group(I)Ljava/lang/String;
    move-result-object v0
    :parse_start
    invoke-static {v0}, Ljava/lang/Long;->parseLong(Ljava/lang/String;)J
    move-result-wide v0
    :parse_end
    .catch Ljava/lang/NumberFormatException; {:parse_start .. :parse_end} :range_parse_failure

    invoke-virtual {p0}, Lorg/cocos2dx/lib/FileTaskHandler;->getTargetFile()Ljava/io/File;
    move-result-object v2
    invoke-virtual {v2}, Ljava/io/File;->length()J
    move-result-wide v2
    cmp-long v4, v0, v2
    if-nez v4, :invalid_range
    iput-wide v2, p0, Lorg/cocos2dx/lib/FileTaskHandler;->_initFileLen:J
    const-wide/16 v0, 0x0
    iput-wide v0, p0, Lorg/cocos2dx/lib/FileTaskHandler;->_lastBytesWritten:J

    :delegate_response
    invoke-super {p0, p1}, Lcom/loopj/android/http/FileAsyncHttpResponseHandler;->sendResponseMessage(Lcz/msebera/android/httpclient/HttpResponse;)V
    return-void

    :range_parse_failure
    move-exception v0
    goto :invalid_range

    :invalid_range
    new-instance v0, Ljava/io/IOException;
    const-string v1, "Content-Range does not match the current download offset"
    invoke-direct {v0, v1}, Ljava/io/IOException;-><init>(Ljava/lang/String;)V
    throw v0
.end method
