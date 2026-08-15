# exfat_fstrim范围溢出

## 构造故障镜像

这个问题不需要额外的构造，直接用一个普通的20M的镜像即可

```bash
dd if=/dev/zero of=exfat.img bs=1M count=20
mkfs.exfat -c 128K exfat.img
```

## 问题复现

### 测试程序

测试程序：`fstrim_ioctl.c`

```c
#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/fs.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	struct fstrim_range range;
	int fd;

	if (argc != 5) {
		fprintf(stderr,
			"Usage: %s <mount-point> <start> <length> <minlen>\n",
			argv[0]);
		return 2;
	}

	range.start = strtoull(argv[2], NULL, 0);
	range.len = strtoull(argv[3], NULL, 0);
	range.minlen = strtoull(argv[4], NULL, 0);

	fd = open(argv[1], O_RDONLY | O_DIRECTORY | O_CLOEXEC);
	if (fd < 0) {
		fprintf(stderr, "open(%s): %s\n",
			argv[1], strerror(errno));
		return 1;
	}

	if (ioctl(fd, FITRIM, &range) < 0) {
		fprintf(stderr, "FITRIM(%s): %s\n",
			argv[1], strerror(errno));
		close(fd);
		return 1;
	}

	close(fd);

	printf("FITRIM completed\n");
	printf("start   : %" PRIu64 " bytes\n", (uint64_t)range.start);
	printf("trimmed : %" PRIu64 " bytes\n", (uint64_t)range.len);
	printf("minlen  : %" PRIu64 " bytes\n", (uint64_t)range.minlen);

	return 0;
}
```

编译：

```bash
gcc -O2 -Wall -Wextra -o fstrim_ioctl strim_ioctl.c
```

### 复现trim len溢出现象

测试脚本`reproduce_exfat_partial_fitrim.sh`

```bash
cat > reproduce_exfat_partial_fitrim.sh <<'EOF'
#!/bin/sh

set -eu

if [ "$#" -ne 2 ]; then
	echo "Usage: $0 <exfat-mount-point> <fstrim-ioctl-binary>" >&2
	exit 2
fi

mountpoint=${1%/}
trim_bin=$2
testdir="$mountpoint/fitrim-range-test"

# 本测试镜像的簇大小为 128 KiB
cluster_size=131072
request_start=0
request_len=$cluster_size

if [ ! -d "$mountpoint" ] || [ ! -x "$trim_bin" ]; then
	echo "Invalid mount point or fstrim binary" >&2
	exit 1
fi

if [ -e "$testdir" ]; then
	echo "Test directory already exists: $testdir" >&2
	exit 1
fi

mkdir "$testdir"

echo "Filling filesystem with 1 MiB files..."

i=1
while [ "$i" -le 64 ]; do
	file=$(printf '%s/file-%02d.bin' "$testdir" "$i")

	if ! dd if=/dev/zero of="$file" \
	    bs=1M count=1 conv=fsync status=none 2>/dev/null; then
		rm -f "$file"
		break
	fi

	i=$((i + 1))
done

last=$((i - 1))

if [ "$last" -lt 3 ]; then
	echo "Not enough files were created" >&2
	exit 1
fi

# 删除位于文件系统中部的文件，在请求范围外产生空闲簇
victim=$((last / 2))
victim_file=$(printf '%s/file-%02d.bin' "$testdir" "$victim")

echo "Deleting $victim_file"
rm -f "$victim_file"
sync

echo
echo "Requesting FITRIM for only $request_len bytes at offset 0"

output=$(
	"$trim_bin" "$mountpoint" \
	    "$request_start" "$request_len" 512
)

echo "$output"

trimmed=$(
	printf '%s\n' "$output" |
	awk '/^trimmed[[:space:]]*:/ { print $3 }'
)

echo

if [ -n "$trimmed" ] && [ "$trimmed" -gt 0 ]; then
	echo "REPRODUCED: kernel reported $trimmed trimmed bytes"
	echo "Expected result: 0 bytes"
	exit 0
fi

echo "Not reproduced: kernel reported zero trimmed bytes"
exit 1
EOF

chmod +x reproduce_exfat_partial_fitrim.sh
```

执行脚本`./reproduce_exfat_partial_fitrim.sh`

<img src="../image/exfat_fstrim范围溢出/image-20260815201040668.png" alt="image-20260815201040668" style="zoom:67%;" />

>问题复现，我们测试脚本里面发起的request_len为1 cluster(131072 bytes)，实际返回的trim len为2 cluster(262144 bytes)

### 复现find_free_bitmap回绕后trim异常

```bash
mkdir /mnt/exfat_fs/wrap-test

i=1
while [ "$i" -le 64 ]; do
	file=$(printf '/mnt/exfat_fs/wrap-test/file-%02d.bin' "$i")
	echo "writing $file"

	dd if=/dev/zero of="$file" \
	   bs=128K count=8 conv=fsync status=none

	if [ "$?" -ne 0 ]; then
		echo "filesystem full at $file"
		# 不要删除这个部分写入的文件
		break
	fi

	i=$((i + 1))
done
```

然后删掉第一个文件

```bash
rm -f /mnt/exfat_fs/wrap-test/file-01.bin
sync
```

执行测试程序

```bash
fstrim_ioctl /mnt/exfat_fs 15M 128K 512
```

<img src="../image/exfat_fstrim范围溢出/image-20260815201414528.png" alt="image-20260815201414528" style="zoom:80%;" />

>写的是回收128K，实际回收了1MB

## 问题修复

https://git.kernel.org/pub/scm/linux/kernel/git/linkinjeon/exfat.git/commit/?h=dev&id=2de727471b3b13409466a4af4f8824a86073bf4b

apply this patch，问题消失，可自行验证！