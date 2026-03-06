# Shared action: optional submodule_branch input

So the workflow can "update to" a given branch (e.g. testing/validate-extension-scripts) instead of
already being pointed at it, the matter_update_submodules action needs an optional input.

**In the shared action repo (matter_update_submodules), on your testing branch:**

## 1. Add optional input

In `action.yml` (or the action definition), add:

```yaml
inputs:
  target_branch:
    description: 'Target branch to update the submodule on'
    required: true
  submodule_branch:
    description: 'Branch (or ref) to update the submodule to. When omitted, same as target_branch.'
    required: false
  app-id:
    ...
```

## 2. Use it in the "Update submodule" step

Replace the submodule fetch/checkout so the ref comes from `submodule_branch` when set, else `target_branch`:

```yaml
    - name: Update submodule
      id: update_submodule
      shell: bash
      run: |
        git submodule update --init third_party/matter_sdk
        short_hash_before=$(cd third_party/matter_sdk && git rev-parse --short HEAD)
        echo "short_hash_before=${short_hash_before}" >> $GITHUB_OUTPUT
        cd third_party/matter_sdk
        SUBMODULE_REF="${{ inputs.submodule_branch || inputs.target_branch }}"
        git fetch origin "$SUBMODULE_REF"
        git checkout "origin/$SUBMODULE_REF"
        cd ../..
        git add third_party/matter_sdk
        if git diff-index --quiet HEAD; then
          echo "empty=true" >> $GITHUB_OUTPUT
          exit 0
        fi
        short_hash=$(cd third_party/matter_sdk && git rev-parse --short HEAD)
        echo "short_hash=${short_hash}" >> $GITHUB_OUTPUT
        echo "pr_branch=update-matter-sdk-${{ inputs.target_branch }}" >> $GITHUB_OUTPUT
```

So when the workflow passes `submodule_branch: testing/validate-extension-scripts`, job 1 will
create a PR that updates the submodule from its current ref to that branch. The repo can stay
on main (submodule at main); the workflow run does the update.
