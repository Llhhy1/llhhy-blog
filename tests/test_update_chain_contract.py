"""v3.18.7 回归：更新链的完整性契约（防 fail-open 回潮）。

背景：第三方独立审计把「在线更新链完整性校验全链 fail-open」判为全仓最高风险——
`sha256.txt` 与它描述的产物走**同一条下载通道**，而脚本里有 4~7 处「取不到校验文件 /
清单里查不到该文件 / 注释校验失败」时**静默 `return 0` 继续安装**的分支，再加上会自动
兜底第三方公共镜像（ghfast / gh-proxy / ghproxy）→ 等价一条远程代码执行通道。

本文件用**静态断言**把这些不变量钉死（不依赖网络、不依赖服务器）：
  1. `update.sh` 不得再出现任何「跳过校验 / 降级为仅比对哈希列表」的措辞；
  2. 不得再自动拼接第三方镜像 URL；
  3. 必须内置非空的 Ed25519 发布公钥，并有强制验签的失败分支；
  4. 必须保留显式逃生舱（`ALLOW_UNSIGNED` / `ALLOW_DOWNGRADE`）与版本单调性；
  5. `deploy.sh` 必须只是 `update.sh` 的薄封装（历史上它是副本，校验逻辑长期更弱）。
"""
import io
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

UPDATE_SH = os.path.join(_ROOT, "update.sh")
DEPLOY_SH = os.path.join(_ROOT, "deploy.sh")

# 曾经的 fail-open 措辞（出现即说明有人把静默跳过改回来了）
FAIL_OPEN_PHRASES = [
    "跳过哈希校验",
    "跳过校验",
    "跳过签名校验",
    "跳过 HMAC",
    "跳过 zip 注释双源校验",
    "仅靠哈希列表比对",
    "降级为仅靠哈希列表比对",
]
# 曾经的第三方镜像（自动兜底 URL）
THIRD_PARTY_MIRRORS = ["https://ghfast.top/", "https://gh-proxy.com/", "https://ghproxy.net/"]


def _read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def test_no_fail_open_phrases_left():
    s = _read(UPDATE_SH)
    for p in FAIL_OPEN_PHRASES:
        assert p not in s, "update.sh 出现 fail-open 措辞：%r（校验不得静默跳过）" % p


def test_no_third_party_mirror_fallback():
    s = _read(UPDATE_SH)
    for m in THIRD_PARTY_MIRRORS:
        assert m not in s, "update.sh 仍在自动兜底第三方镜像 %s（校验清单与产物同通道，可被同时改写）" % m
    # 显式配置入口必须保留（否则网络不通的用户无法自建代理）
    assert 'GH_MIRROR="${GH_MIRROR:-}"' in s, "update.sh 缺少显式 GH_MIRROR 配置入口"


def test_builtin_pubkey_present_and_enforced():
    s = _read(UPDATE_SH)
    m = re.search(r'BUILTIN_RELEASE_PUBKEY="([^"]*)"', s)
    assert m, "update.sh 缺少 BUILTIN_RELEASE_PUBKEY"
    assert m.group(1).strip(), "BUILTIN_RELEASE_PUBKEY 为空——验签会 fail-closed 拒绝一切更新"
    assert "RELEASE_PUBKEY" in s, "缺少 RELEASE_PUBKEY 覆盖入口（自建发布者要用）"
    # 验签失败必须是硬失败
    assert "发布物签名校验失败" in s
    assert "Ed25519PublicKey" in s, "update.sh 内联验签代码缺失"


def test_escape_hatches_and_version_monotonic():
    s = _read(UPDATE_SH)
    assert 'ALLOW_UNSIGNED="${ALLOW_UNSIGNED:-0}"' in s, "逃生舱必须默认关闭"
    assert 'ALLOW_DOWNGRADE="${ALLOW_DOWNGRADE:-0}"' in s, "降级必须默认拒绝"
    assert "sort -V" in s, "缺少版本单调性比较"


def test_deploy_sh_is_thin_delegate():
    s = _read(DEPLOY_SH)
    assert len(s) < 4000, "deploy.sh 又变胖了（历史上它是 update.sh 的副本，会与主链漂移）"
    assert "update.sh" in s and "exec bash" in s, "deploy.sh 应是 update.sh 的薄封装"
    for p in FAIL_OPEN_PHRASES:
        assert p not in s, "deploy.sh 出现 fail-open 措辞：%r" % p


def test_stale_workdir_files_are_cleaned():
    """v3.18.8：$WORK 跨轮复用，旧的 sha256.txt 必须清掉。

    实测教训：v3.18.7 上线时，第一轮更新遗留的 `/tmp/llhhy_update/sha256.txt` 被拿来
    跟新一版的 `sha256.txt.sig` 配对比对 → 必然验签失败（虽然 fail-closed 正确地拦住了
    安装，站点未受影响，但更新被无谓地阻断）。所以「先清旧清单再下载」必须固化。
    """
    s = _read(UPDATE_SH)
    assert 'rm -f "$WORK"/sha256.txt' in s, "缺少工作目录里旧清单的清理（会导致跨轮验签失败）"
    assert "rm -f sha256.txt sha256.txt.sig" in s, "验签前未丢弃旧清单"
    # 验签函数内部必须自己下载清单（不能依赖调用方先下载）
    assert 'gh_fetch "$CHECKSUM_URL" "sha256.txt"' in s
    assert 'gh_fetch "$SIG_URL" "sha256.txt.sig"' in s


def test_gh_mirror_is_tried_first_when_configured():
    """v3.25.15：传了 GH_MIRROR 就必须真的先走镜像，否则白等直连 2×180s。

    实测教训：v3.25.14 部署时明确传了 GH_MIRROR='https://gh-proxy.com/'（873 KB/s），
    但 `try_urls` 把直连排在最前（21 KB/s），后端包走直连耗 **133 秒**才下完，
    镜像根本没轮上——「配了镜像」和「用上镜像」是两件事。
    """
    s = _read(UPDATE_SH)
    assert 'GH_MIRROR_FIRST="${GH_MIRROR_FIRST:-1}"' in s, "缺少 GH_MIRROR_FIRST 开关（默认应为 1）"
    assert 'try_urls=("${GH_MIRROR}${url}" "$url")' in s, "配了 GH_MIRROR 时必须镜像优先、直连兜底"
    # 前置条件：必须同时满足「显式配了镜像」+「开关为 1」，
    # 否则未配置 GH_MIRROR 时会拼出空前缀的 URL。
    assert re.search(
        r'if \[ -n "\$GH_MIRROR" \] && \[ "\$GH_MIRROR_FIRST" = "1" \]', s
    ), "镜像优先分支必须同时校验 GH_MIRROR 非空与 GH_MIRROR_FIRST=1"
    # 旧顺序要能显式取回（GH_MIRROR_FIRST=0）
    assert 'try_urls=("$url")' in s, "缺少 GH_MIRROR_FIRST=0 时的直连优先分支"


def test_scripts_are_lf_only():
    """服务器上 CRLF 的 bash 脚本会直接语法报错（历史事故）。"""
    for p in (UPDATE_SH, DEPLOY_SH):
        with open(p, "rb") as f:
            b = f.read()
        assert b.count(b"\r\n") == 0, "%s 含 CRLF 行尾" % os.path.basename(p)
        assert b.count(b"\r") == 0, "%s 含孤立 CR" % os.path.basename(p)
