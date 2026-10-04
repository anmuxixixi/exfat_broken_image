# android_clu_count_overflow介绍

## CVE介绍

9月安卓官网发布了最新的安全报告: https://source.android.com/docs/security/bulletin/2026/2026-09-01?hl=zh-tw

- 其中有一个漏洞涉及到exfatprogs: <u>CVE-2026-45531</u>
- 安卓的修改链接为: https://android.googlesource.com/platform/external/exfatprogs/+/5ec5ede9ba508dde0c2cc95363742f2c2f669fff

走读了代码以觉得其实还好，本身fsck的修复逻辑没有问题，如果硬说可以作为一个攻击点使fsck.exfat越界，只能说勉强可以作为一个C语言的规范整改。

## 本地复现

编译:
```
./configure \
  CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
  LDFLAGS="-fsanitize=address,undefined"

make -j"$(nproc)"
```

故障注入:
```shell
dd if=/dev/zero of=exfat.img bs=1M count=10
mkfs.exfat exfat.img
python repro_build.py exfat.img
mkfs.exfat -n exfat.img
```

复现:
```shell
root@iZuf62iu4ebdrfah86j43wZ:~/exfatprogs/0924_CVE/exfatprogs# ./fsck/fsck.exfat -n exfat.img
exfatprogs version : 1.4.3 (2026-08-14)
fsck.c:450:38: runtime error: unsigned integer overflow: 18446744073709551615 * 512 cannot be represented in type 'unsigned long'
SUMMARY: UndefinedBehaviorSanitizer: undefined-behavior fsck.c:450:38 in
too large sector count: 18446744073709551615, expected: 20480
boot region is corrupted. try to restore the region from backup. Fix (y/N)? 
```