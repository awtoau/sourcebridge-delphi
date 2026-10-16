#!/usr/bin/env bash
set -euo pipefail

destination="${1:?usage: bootstrap_fpc_test_corpus.sh DESTINATION}"
revision="${FPC_TEST_REVISION:-82947b0dc135313b2bd64c208025de4bc81b2c2f}"
remote="https://gitlab.com/freepascal.org/fpc/source.git"

if [[ -e "$destination" ]]; then
    echo "Destination already exists: $destination" >&2
    exit 1
fi

git clone --filter=blob:none --no-checkout "$remote" "$destination"
git -C "$destination" sparse-checkout init --cone
git -C "$destination" sparse-checkout set tests rtl packages
git -C "$destination" fetch --depth 1 origin "$revision"
git -C "$destination" checkout --detach "$revision"
echo "Pinned FPC compiler test corpus at $destination@$revision"
