package org.cocos2dx.lib;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Set;

/** Keeps public staging bundle transport partials outside native StartScene cleanup. */
public final class AkaineBundlePartialCache {
    private static final String PREFIX = "https://cdn.akai.id.vn/arkane-test-bundle/";
    private static final long MAX_STALE_BYTES = 2L * 1024 * 1024 * 1024;
    private static final long MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000;
    private static final int MAX_STALE_FILES = 16;
    private static final Set<String> ACTIVE = new HashSet<String>();

    public static synchronized File select(File temporary, String url, File destination) {
        try {
            File root = destination.getParentFile().getParentFile();
            String path = root.getAbsolutePath();
            String canonical = root.getCanonicalPath();
            if (!(path.equals("/data/user/0/akai.arc.lmao/files")
                    || path.equals("/data/data/akai.arc.lmao/files"))
                    || !(canonical.equals("/data/user/0/akai.arc.lmao/files")
                    || canonical.equals("/data/data/akai.arc.lmao/files"))) return temporary;
            return selectForRoot(temporary, url, destination, root);
        } catch (Exception ignored) {
            return temporary;
        }
    }

    private static File selectForRoot(File temporary, String url, File destination, File root) {
        try {
            if (url == null || !url.startsWith(PREFIX)
                    || !url.substring(PREFIX.length()).matches("7[.]0[.]255-staging-assets-[A-Za-z0-9_-]{1,160}[.]cb")
                    || !destination.getName().matches("[0-9]{1,4}(?:[.][0-9]{1,4}){3}_[0-9]{1,3}[.]bundle")
                    || !root.isDirectory() || !root.canWrite()) return temporary;
            File canonicalRoot = root.getCanonicalFile();
            String expected = new File(new File(canonicalRoot, "dltemp"), destination.getName()).getPath();
            if (!destination.getAbsolutePath().equals(new File(new File(root, "dltemp"), destination.getName()).getAbsolutePath())
                    || !destination.getCanonicalPath().equals(expected)
                    || !temporary.getAbsolutePath().equals(destination.getAbsolutePath() + ".tmp")
                    || !temporary.getCanonicalPath().equals(expected + ".tmp")) return temporary;
            File cache = new File(canonicalRoot, "bundle-partials");
            if ((!cache.isDirectory() && !cache.mkdir()) || !cache.canWrite()
                    || !cache.getCanonicalFile().equals(cache)) return temporary;
            prune(cache);
            StringBuilder key = new StringBuilder();
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                    (url + "\n" + destination.getName()).getBytes(StandardCharsets.UTF_8));
            for (byte value : digest) key.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
            File partial = new File(cache, key.toString() + ".part");
            String path = partial.getAbsolutePath();
            if (ACTIVE.contains(path) || !partial.getCanonicalFile().equals(partial)
                    || (partial.exists() && (!partial.isFile() || !partial.canRead() || !partial.canWrite()))) return temporary;
            try (RandomAccessFile writable = new RandomAccessFile(partial, "rw")) {
                // Opening verifies write access without changing a retained prefix.
            }
            if (!partial.setLastModified(System.currentTimeMillis())) return temporary;
            ACTIVE.add(path);
            return partial;
        } catch (Exception ignored) {
            return temporary;
        }
    }

    private static void prune(File cache) throws IOException {
        File[] files = cache.listFiles();
        if (files == null) throw new IOException("Bundle partial cache is unreadable");
        long bytes = 0;
        int count = 0;
        long oldest = System.currentTimeMillis() - MAX_AGE_MS;
        for (File file : files) {
            if (!file.getName().matches("[0-9a-f]{64}[.]part") || !file.isFile()
                    || !file.getCanonicalFile().equals(file)) throw new IOException("Unexpected bundle partial cache entry");
            if (ACTIVE.contains(file.getAbsolutePath())) continue;
            if (file.lastModified() < oldest || file.length() > MAX_STALE_BYTES) {
                if (!file.delete()) throw new IOException("Cannot remove stale bundle partial");
            } else {
                bytes += file.length();
                count++;
            }
        }
        while (count > MAX_STALE_FILES || bytes > MAX_STALE_BYTES) {
            File oldestFile = null;
            for (File file : files) {
                if (!file.exists() || ACTIVE.contains(file.getAbsolutePath())) continue;
                if (oldestFile == null || file.lastModified() < oldestFile.lastModified()) oldestFile = file;
            }
            if (oldestFile == null) throw new IOException("Cannot find stale bundle partial");
            long length = oldestFile.length();
            if (!oldestFile.delete()) throw new IOException("Cannot bound stale bundle partials");
            bytes -= length;
            count--;
        }
    }

    public static synchronized void release(File partial) {
        if (partial != null) ACTIVE.remove(partial.getAbsolutePath());
    }

    public static synchronized void begin(FileTaskHandler handler) throws IOException {
        if (handler._akaineCacheCancelled || handler._akaineCacheReleased)
            throw new IOException("Cancelled bundle partial handler cannot write");
        if (ACTIVE.contains(handler.getTargetFile().getAbsolutePath())) handler._akaineCacheWriting = true;
    }

    public static synchronized void end(FileTaskHandler handler) {
        handler._akaineCacheWriting = false;
        if (handler._akaineCacheCancelled) finished(handler);
    }

    public static synchronized void cancelled(FileTaskHandler handler) {
        if (handler._akaineCacheReleased) return;
        if (handler._akaineCacheWriting || ACTIVE.contains(handler.getTargetFile().getAbsolutePath())) {
            handler._akaineCacheCancelled = true;
            if (!handler._akaineCacheWriting) finished(handler);
        }
    }

    public static synchronized void finished(FileTaskHandler handler) {
        if (handler._akaineCacheReleased || handler._akaineCacheWriting) return;
        handler._akaineCacheReleased = true;
        release(handler.getTargetFile());
    }

    public static synchronized void failed(int status, File partial) {
        if (status != 416 || partial == null || !ACTIVE.contains(partial.getAbsolutePath())) return;
        try {
            if (partial.isFile() && partial.getCanonicalFile().equals(partial)) partial.delete();
        } catch (IOException ignored) {
            // A failed deletion preserves the partial; the original failure still reaches native code.
        }
    }
}
