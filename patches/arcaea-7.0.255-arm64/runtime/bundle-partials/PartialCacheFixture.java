package org.cocos2dx.lib;

import java.io.File;
import java.io.RandomAccessFile;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Set;

/** Actual helper, real disposable files; only the Android app root is adapted. */
public final class PartialCacheFixture {
    private static final String URL = "https://cdn.akai.id.vn/bundle/7.0.255-prod-original-base25-20261027_0.cb";
    private static final byte[] PREFIX = {19, 2, 91, 17, -8, 23};
    private static Method select;
    private static int cases;
    private static int assertions;

    private static void check(boolean ok) {
        assertions++;
        if (!ok) throw new AssertionError("case=" + cases + ", assertion=" + assertions);
    }

    private static File choose(File root, String url, File destination, File temporary) throws Exception {
        return (File) select.invoke(null, temporary, url, destination, root);
    }

    private static File choose(File root, String url, String name) throws Exception {
        File destination = new File(new File(root, "dltemp"), name);
        return choose(root, url, destination, new File(destination.getPath() + ".tmp"));
    }

    private static void length(File file, long size) throws Exception {
        try (RandomAccessFile value = new RandomAccessFile(file, "rw")) { value.setLength(size); }
    }

    private static File fresh(File directory, String name) throws Exception {
        File root = new File(directory, name).getCanonicalFile();
        check(new File(root, "dltemp").mkdirs());
        return root;
    }

    private static void clearActive() throws Exception {
        Field active = AkaineBundlePartialCache.class.getDeclaredField("ACTIVE");
        active.setAccessible(true);
        ((Set<?>) active.get(null)).clear();
    }

    public static void main(String[] args) throws Exception {
        select = AkaineBundlePartialCache.class.getDeclaredMethod("selectForRoot", File.class, String.class, File.class, File.class);
        select.setAccessible(true);
        File directory = new File(args[0]).getCanonicalFile();
        File root = fresh(directory, "restart");
        String name = "7.0.255.25_0.bundle";
        File destination = new File(root, "dltemp/" + name);
        File temporary = new File(destination.getPath() + ".tmp");

        cases++; File first = choose(root, URL, destination, temporary);
        check(first.getParentFile().equals(new File(root, "bundle-partials")));
        Files.write(first.toPath(), PREFIX);
        check(choose(root, URL, destination, temporary).equals(temporary));
        check(Arrays.equals(Files.readAllBytes(first.toPath()), PREFIX));

        cases++; clearActive(); // Simulates the loss of static state on force-stop.
        Files.write(temporary.toPath(), new byte[] {9});
        check(temporary.delete() && destination.getParentFile().delete());
        check(destination.getParentFile().mkdir());
        File resumed = choose(root, URL, destination, temporary);
        check(resumed.equals(first) && Arrays.equals(Files.readAllBytes(resumed.toPath()), PREFIX));

        cases++; AkaineBundlePartialCache.release(resumed);
        check(choose(root, URL, destination, temporary).equals(first));
        File delta = choose(root, URL.replace("prod-original-base25-20261027_0", "prod-collapse-from14-20261022"), name);
        check(!delta.equals(first) && delta.length() == 0);
        File version = choose(root, URL, "7.0.255.26_0.bundle");
        check(!version.equals(first) && version.length() == 0);
        File part = choose(root, URL, "7.0.255.25_1.bundle");
        check(!part.equals(first) && part.length() == 0);

        cases++;
        String[] acceptedFallbacks = {
            URL.replace("prod-original-base25-20261027_0", "prod-collapse-full-20261022_0"),
            URL.replace("prod-original-base25-20261027_0", "prod-collapse-full-20261022_6"),
            URL.replace("_0.cb", "_9.cb")};
        for (String url : acceptedFallbacks) {
            File accepted = choose(root, url, name);
            check(accepted.getParentFile().equals(new File(root, "bundle-partials")));
            AkaineBundlePartialCache.release(accepted);
        }

        String[] denied = {null, URL + "?token=fixture", URL + "#fragment", URL.replace("https:", "http:"),
            URL.replace("cdn.akai.id.vn", "cdn.akai.id.vn.evil.invalid"), URL.replace("cdn.akai", "user@cdn.akai"),
            URL.replace(".vn/", ".vn:443/"), URL.replace("_0.cb", "_0.json"), URL.replace("_0.cb", "/_0.cb"),
            URL.replace("_0.cb", "%2f0.cb"), URL.replace(".vn/bundle/", ".vn/songs/"),
            URL.replace("prod-original", "../../prod-original"), URL + "/bad", URL.replace("prod-original", new String(new char[161]).replace('\0', 'a')),
            URL.replace(".vn/bundle/", ".vn/arkane-test-bundle/"),
            URL.replace("prod-original-base25-20261027_0", "staging-assets-thin21-20261024_0"),
            URL.replace("base25", "base26"), URL.replace("_0.cb", "_10.cb"),
            URL.replace("prod-original-base25-20261027_0", "prod-collapse-full-20261022_7"),
            URL.replace("prod-original-base25-20261027_0", "prod-collapse-from15-20261022")};
        for (String url : denied) {
            cases++; check(choose(root, url, destination, temporary).equals(temporary));
        }

        cases++; check(AkaineBundlePartialCache.select(temporary, URL, destination).equals(temporary));
        File wrongFinal = new File(root, "songs/" + name);
        check(choose(root, URL, wrongFinal, new File(wrongFinal.getPath() + ".tmp")).getPath().equals(wrongFinal.getPath() + ".tmp"));
        check(choose(root, URL, destination, new File(destination.getPath() + ".other")).getName().endsWith(".other"));
        check(choose(root, URL, "song.aff").getName().equals("song.aff.tmp"));

        cases++; File redirected = new File(temporary.getPath()) {
            public String getCanonicalPath() { return new File(root, "outside").getAbsolutePath(); }
        };
        check(choose(root, URL, destination, redirected).equals(redirected));
        File readOnlyRoot = new File(root.getPath()) { public boolean canWrite() { return false; } };
        check(choose(readOnlyRoot, URL, destination, temporary).equals(temporary));

        cases++; File foreignRoot = fresh(directory, "foreign-entry");
        File foreignCache = new File(foreignRoot, "bundle-partials"); check(foreignCache.mkdir());
        File foreign = new File(foreignCache, "unrelated.keep"); Files.write(foreign.toPath(), PREFIX);
        check(choose(foreignRoot, URL, name).getName().endsWith(".tmp"));
        check(Arrays.equals(Files.readAllBytes(foreign.toPath()), PREFIX));

        cases++; File capped = fresh(directory, "count-cap");
        File cappedCache = new File(capped, "bundle-partials"); check(cappedCache.mkdir());
        long now = System.currentTimeMillis();
        for (int index = 0; index < 20; index++) {
            File stale = new File(cappedCache, String.format("%064x.part", index));
            Files.write(stale.toPath(), PREFIX); check(stale.setLastModified(now - 200000 + index * 1000));
        }
        File selected = choose(capped, URL, name);
        check(cappedCache.listFiles().length == 17); // 16 stale plus this active partial.
        check(!new File(cappedCache, String.format("%064x.part", 0)).exists());
        check(Arrays.equals(Files.readAllBytes(first.toPath()), PREFIX));

        cases++; check(selected.setLastModified(now - 8L * 24 * 60 * 60 * 1000));
        Files.write(selected.toPath(), PREFIX);
        check(selected.setLastModified(now - 8L * 24 * 60 * 60 * 1000));
        choose(capped, URL.replace("_0.cb", "_1.cb"), name);
        check(Arrays.equals(Files.readAllBytes(selected.toPath()), PREFIX));
        AkaineBundlePartialCache.release(selected);
        choose(capped, URL.replace("_0.cb", "_2.cb"), name);
        check(!selected.exists());

        cases++; File capacity = fresh(directory, "byte-cap");
        File capacityCache = new File(capacity, "bundle-partials"); check(capacityCache.mkdir());
        File largeA = new File(capacityCache, String.format("%064x.part", 31));
        File largeB = new File(capacityCache, String.format("%064x.part", 32));
        length(largeA, 1100L * 1024 * 1024); length(largeB, 1100L * 1024 * 1024);
        check(largeA.setLastModified(now - 5000)); check(largeB.setLastModified(now - 4000));
        choose(capacity, URL, name);
        check(!largeA.exists() && largeB.length() == 1100L * 1024 * 1024);

        cases++; check(resumed.renameTo(destination));
        AkaineBundlePartialCache.release(resumed);
        File afterSuccess = choose(root, URL, destination, temporary);
        check(afterSuccess.length() == 0 && Arrays.equals(Files.readAllBytes(destination.toPath()), PREFIX));

        cases++; File readonly = fresh(directory, "readonly-file");
        File readonlyPartial = choose(readonly, URL, name); AkaineBundlePartialCache.release(readonlyPartial);
        check(readonlyPartial.setReadOnly());
        if (!readonlyPartial.canWrite()) check(choose(readonly, URL, name).getName().endsWith(".tmp"));
        else throw new AssertionError("OS did not expose read-only file; fixture requires honest coverage");
        check(readonlyPartial.setWritable(true));

        cases++; File failureRoot = fresh(directory, "status-retry");
        File failure = choose(failureRoot, URL, name); Files.write(failure.toPath(), PREFIX);
        AkaineBundlePartialCache.failed(206, failure);
        check(Arrays.equals(Files.readAllBytes(failure.toPath()), PREFIX));
        AkaineBundlePartialCache.failed(503, failure);
        check(Arrays.equals(Files.readAllBytes(failure.toPath()), PREFIX));
        AkaineBundlePartialCache.failed(416, failure);
        check(!failure.exists());
        AkaineBundlePartialCache.release(failure);
        File retry = choose(failureRoot, URL, name);
        check(retry.equals(failure) && retry.length() == 0);
        File noncache = new File(failureRoot, "unrelated"); Files.write(noncache.toPath(), PREFIX);
        AkaineBundlePartialCache.failed(416, noncache);
        check(Arrays.equals(Files.readAllBytes(noncache.toPath()), PREFIX));

        cases++; File cancelledRoot = fresh(directory, "cancel-before-body");
        File cancelledFile = choose(cancelledRoot, URL, name); Files.write(cancelledFile.toPath(), PREFIX);
        FileTaskHandler cancelled = new FileTaskHandler(null, 1, cancelledFile, new File(cancelledRoot, "dltemp/" + name));
        AkaineBundlePartialCache.cancelled(cancelled);
        check(cancelled._akaineCacheCancelled && cancelled._akaineCacheReleased);
        File replacement = choose(cancelledRoot, URL, name);
        check(replacement.equals(cancelledFile));
        boolean blocked = false;
        try { AkaineBundlePartialCache.begin(cancelled); } catch (java.io.IOException expected) { blocked = true; }
        check(blocked && Arrays.equals(Files.readAllBytes(replacement.toPath()), PREFIX));
        AkaineBundlePartialCache.finished(cancelled);
        check(choose(cancelledRoot, URL, name).getName().endsWith(".tmp"));

        cases++; File writingRoot = fresh(directory, "cancel-during-body");
        File writingFile = choose(writingRoot, URL, name); Files.write(writingFile.toPath(), PREFIX);
        FileTaskHandler writing = new FileTaskHandler(null, 1, writingFile, new File(writingRoot, "dltemp/" + name));
        AkaineBundlePartialCache.begin(writing); AkaineBundlePartialCache.cancelled(writing);
        check(writing._akaineCacheWriting && !writing._akaineCacheReleased);
        check(choose(writingRoot, URL, name).getName().endsWith(".tmp"));
        AkaineBundlePartialCache.end(writing);
        check(!writing._akaineCacheWriting && writing._akaineCacheReleased);
        check(choose(writingRoot, URL, name).equals(writingFile));
        AkaineBundlePartialCache.finished(writing); AkaineBundlePartialCache.cancelled(writing);
        check(choose(writingRoot, URL, name).getName().endsWith(".tmp"));

        System.out.println("PASS cases=" + cases + " assertions=" + assertions
            + "; actual helper; disposable filesystem; Android root and canonical mismatch adapters; no HTTP/runtime claim");
    }
}
