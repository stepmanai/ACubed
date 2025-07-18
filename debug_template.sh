cd "$(dirname "$0")";
export UV_CACHE_DIR=".cache";
rm -rf tmp && mkdir -p $_ && cd $_;

copier copy \
    --vcs-ref main \
    --data project_name="lorem-ipsum" \
    --data project_description="Lorem ipsum dolor sit amet." \
    --exclude README.md \
    --exclude debug_template.sh \
    ../ ./;

make install;
uv run pre-commit run --files *;
