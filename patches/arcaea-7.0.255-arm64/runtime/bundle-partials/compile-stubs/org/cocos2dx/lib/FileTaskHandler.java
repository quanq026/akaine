package org.cocos2dx.lib;
import java.io.File;
import java.io.IOException;
import cz.msebera.android.httpclient.HttpEntity;
/** Compile-time adapter only; never include this class in a fixture jar or candidate DEX. */
class FileTaskHandler {
    boolean _akaineCacheCancelled, _akaineCacheWriting, _akaineCacheReleased;
    File file;
    FileTaskHandler(Cocos2dxDownloader downloader, int id, File file, File destination) { this.file = file; }
    public File getTargetFile() { return file; }
    protected byte[] getResponseData(HttpEntity entity) throws IOException { return null; }
    public void onCancel() {}
    public void onFinish() {}
}
