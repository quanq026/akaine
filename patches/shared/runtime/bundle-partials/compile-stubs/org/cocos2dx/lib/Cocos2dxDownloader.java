package org.cocos2dx.lib;

/** Callback sink for the real FileTaskHandler fixture; no native game calls. */
public final class Cocos2dxDownloader {
    public void onFinish(int id, int code, String reason, byte[] data) {}
    public void runNextTaskIfExists() {}
    public void onProgress(int id, long delta, long current, long total) {}
    public void onStart(int id) {}
}
