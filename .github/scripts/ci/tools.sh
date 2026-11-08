#!/usr/bin/env bash
# Pinned CI tools (D1-04). Sourced by the job scripts, never executed directly.
#
#   TRUFFLEHOG=$(ensure_tool trufflehog)   # prints the absolute path of a binary with the pinned version
#
# Resolution order: a binary on PATH whose version matches exactly, then the cache, then a download.
# Cache: ${XDG_CACHE_HOME:-$HOME/.cache}/apex-ci-tools/<tool>-<version>/ (outside the repository).
# Downloads are checked against the SHA-256 pinned below before anything is unpacked (fail closed).
# A cached binary is re-checked against the hash recorded when it was installed; on mismatch it is
# discarded and downloaded again.
# To bump a tool: change its version, then copy the four SHA-256 values from the release's checksum
# file (trufflehog and actionlint publish one; shellcheck's are the release asset digests).

TRUFFLEHOG_VERSION=3.99.8
ACTIONLINT_VERSION=1.7.12
SHELLCHECK_VERSION=0.11.0

_tools_fail() {
  echo "ERROR: $*" >&2
  exit 1
}

_tool_platform() {
  local os arch
  case "$(uname -s)" in
    Linux) os=linux ;;
    Darwin) os=darwin ;;
    *) _tools_fail "unsupported OS for pinned CI tools: $(uname -s)" ;;
  esac
  case "$(uname -m)" in
    x86_64 | amd64) arch=amd64 ;;
    arm64 | aarch64) arch=arm64 ;;
    *) _tools_fail "unsupported architecture for pinned CI tools: $(uname -m)" ;;
  esac
  echo "${os}-${arch}"
}

_tool_version() {
  case "$1" in
    trufflehog) echo "$TRUFFLEHOG_VERSION" ;;
    actionlint) echo "$ACTIONLINT_VERSION" ;;
    shellcheck) echo "$SHELLCHECK_VERSION" ;;
    *) _tools_fail "unknown CI tool: $1" ;;
  esac
}

# Release archive for <tool> on <platform> (os-arch).
_tool_archive() {
  local tool=$1 os=${2%-*} arch=${2#*-}
  case "$tool" in
    trufflehog) echo "trufflehog_${TRUFFLEHOG_VERSION}_${os}_${arch}.tar.gz" ;;
    actionlint) echo "actionlint_${ACTIONLINT_VERSION}_${os}_${arch}.tar.gz" ;;
    shellcheck)
      local sc_arch=$arch
      [ "$arch" = amd64 ] && sc_arch=x86_64
      [ "$arch" = arm64 ] && sc_arch=aarch64
      echo "shellcheck-v${SHELLCHECK_VERSION}.${os}.${sc_arch}.tar.xz"
      ;;
  esac
}

_tool_url() {
  local tool=$1 archive=$2
  case "$tool" in
    trufflehog) echo "https://github.com/trufflesecurity/trufflehog/releases/download/v${TRUFFLEHOG_VERSION}/${archive}" ;;
    actionlint) echo "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/${archive}" ;;
    shellcheck) echo "https://github.com/koalaman/shellcheck/releases/download/v${SHELLCHECK_VERSION}/${archive}" ;;
  esac
}

# SHA-256 of the release archive, per tool and platform (os-arch). Checked before unpacking.
_tool_sha256() {
  case "$1-$2" in
    trufflehog-linux-amd64) echo 7c3b02f160f28929a467e29e20fba98746e0729f6e37c3c25761e4f8789abe08 ;;
    trufflehog-linux-arm64) echo a0382d83dd58c967af5dd0175cc732c62c836ab1d15dc9ae71b01a2d3f0911b2 ;;
    trufflehog-darwin-amd64) echo f77c01a484eb8ba7ce5a17ec08ef72d3c6398ff0513b4c7b7dc480c50d8e5176 ;;
    trufflehog-darwin-arm64) echo 85724f221bc390f6e0bdf65df245468c8426350de85aa9290ea5491c6d4ec35a ;;
    actionlint-linux-amd64) echo 8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8 ;;
    actionlint-linux-arm64) echo 325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6 ;;
    actionlint-darwin-amd64) echo 5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644 ;;
    actionlint-darwin-arm64) echo aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f ;;
    shellcheck-linux-amd64) echo 8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198 ;;
    shellcheck-linux-arm64) echo 12b331c1d2db6b9eb13cfca64306b1b157a86eb69db83023e261eaa7e7c14588 ;;
    shellcheck-darwin-amd64) echo 3c89db4edcab7cf1c27bff178882e0f6f27f7afdf54e859fa041fca10febe4c6 ;;
    shellcheck-darwin-arm64) echo 56affdd8de5527894dca6dc3d7e0a99a873b0f004d7aabc30ae407d3f48b0a79 ;;
    *) _tools_fail "no pinned SHA-256 for $1 on $2" ;;
  esac
}

_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# verify_sha256 <file> <expected>: returns 1 and says what happened on mismatch.
verify_sha256() {
  local actual
  actual="$(_sha256 "$1")"
  if [ "$actual" != "$2" ]; then
    echo "ERROR: SHA-256 mismatch for $1" >&2
    echo "  expected $2" >&2
    echo "  actual   $actual" >&2
    return 1
  fi
  echo "sha256 ok: $(basename "$1")" >&2
}

# True when the binary reports exactly the pinned version (not a longer one such as 3.99.80).
_version_matches() {
  local out pattern
  out="$("$1" --version 2>&1 || true)"
  pattern="$(printf '%s' "$2" | sed 's/\./\\./g')"
  echo "$out" | grep -Eq "(^|[^0-9.])${pattern}([^0-9.]|\$)"
}

ensure_tool() {
  local tool=$1 version platform archive url sha dir bin part extract found
  version="$(_tool_version "$tool")"

  if command -v "$tool" >/dev/null 2>&1 && _version_matches "$(command -v "$tool")" "$version"; then
    command -v "$tool"
    return 0
  fi

  platform="$(_tool_platform)"
  dir="${XDG_CACHE_HOME:-$HOME/.cache}/apex-ci-tools/${tool}-${version}"
  bin="${dir}/${tool}"

  if [ -x "$bin" ] && [ -f "$bin.sha256" ] && [ "$(_sha256 "$bin")" = "$(cat "$bin.sha256")" ] \
    && _version_matches "$bin" "$version"; then
    echo "$bin"
    return 0
  fi
  if [ -e "$bin" ]; then
    echo "cached ${tool} failed its integrity check; discarding it and downloading again" >&2
    rm -f "$bin" "$bin.sha256"
  fi

  archive="$(_tool_archive "$tool" "$platform")"
  url="$(_tool_url "$tool" "$archive")"
  sha="$(_tool_sha256 "$tool" "$platform")"
  part="${dir}/${archive}"
  extract="${dir}/extract"

  mkdir -p "$dir"
  echo "downloading ${tool} ${version} (${platform}) from ${url}" >&2
  curl -fsSL --retry 3 -o "$part" "$url" || _tools_fail "download failed: $url"
  if ! verify_sha256 "$part" "$sha"; then
    rm -f "$part"
    _tools_fail "refusing to unpack ${archive}"
  fi

  rm -rf "$extract"
  mkdir -p "$extract"
  tar -xf "$part" -C "$extract" || _tools_fail "could not unpack ${archive}"
  found="$(find "$extract" -type f -name "$tool" | sed -n '1p')"
  [ -n "$found" ] || _tools_fail "${tool} not found inside ${archive}"
  mv -f "$found" "$bin"
  chmod 0755 "$bin"
  rm -rf "$extract" "$part"

  _sha256 "$bin" >"$bin.sha256"
  _version_matches "$bin" "$version" || _tools_fail "downloaded ${tool} does not report version ${version}"
  echo "$bin"
}
