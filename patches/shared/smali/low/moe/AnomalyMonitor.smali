.class public final Llow/moe/AnomalyMonitor;
.super Ljava/lang/Object;
.source "AnomalyMonitor.java"


# static fields
.field private static available:Z


# direct methods
.method static constructor <clinit>()V
    .registers 2

    .line 9
    :try_start_0
    const-string v0, "akaineanomaly_monitor"

    invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V

    .line 10
    const/4 v0, 0x1

    sput-boolean v0, Llow/moe/AnomalyMonitor;->available:Z
    :try_end_8
    .catch Ljava/lang/UnsatisfiedLinkError; {:try_start_0 .. :try_end_8} :catch_9

    .line 13
    goto :goto_11

    .line 11
    :catch_9
    move-exception v0

    .line 12
    const-string v0, "AkaineAnomalyMonitor"

    const-string v1, "diagnostic_library_unavailable"

    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I

    .line 14
    :goto_11
    return-void
.end method

.method private constructor <init>()V
    .registers 1

    .line 16
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V

    return-void
.end method

.method public static frame()V
    .registers 1

    .line 21
    sget-boolean v0, Llow/moe/AnomalyMonitor;->available:Z

    if-eqz v0, :cond_7

    invoke-static {}, Llow/moe/AnomalyMonitor;->frameNative()V

    .line 22
    :cond_7
    return-void
.end method

.method private static native frameNative()V
.end method

.method public static prepare()V
    .registers 2

    sget-boolean v0, Llow/moe/AnomalyMonitor;->available:Z
    if-eqz v0, :done
    :try_start
    invoke-static {}, Llow/moe/AnomalyMonitor;->prepareNative()Z
    :try_end
    .catch Ljava/lang/LinkageError; {:try_start .. :try_end} :unavailable
    return-void
    :unavailable
    move-exception v0
    const-string v0, "AkainePacks"
    const-string v1, "early_prepare_unavailable"
    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
    :done
    return-void
.end method

.method private static native prepareNative()Z
.end method
