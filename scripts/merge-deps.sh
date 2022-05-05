git fetch --prune
git checkout -b merge-deps
git reset --hard origin/main

for branch in `git branch -a | grep dependabot/pip`; do
    git merge $branch
    git checkout --theirs poetry.lock
    poetry lock --no-update
    git add poetry.lock
    git commit
done;
