#!/usr/bin/env python
import click
from datetime import datetime
from subprocess import call, check_call, check_output, PIPE
import sys

DATABRICKS_REMOTE = "git@github.com:databricks/tensorframes.git"
PUBLISH_MODES = {
    "local": "tfs_testing/publishLocal",
    "m2": "tfs_testing/publishM2",
    "spark-package-publish": "distribution/spDist",
}

WORKING_BRANCH = "WORKING_BRANCH_RELEASE_%s_@%s"
# lower case "z" puts the branch at the end of the github UI.
RELEASE_TAG = "v%s"


def prominentPrint(x):
    click.echo(click.style(x, underline=True))


def verify(prompt, interactive):
    if not interactive:
        return True
    return click.confirm(prompt, show_default=True)


@click.command()
@click.argument("release-version", type=str)
@click.argument("next-version", type=str)
@click.option("--publish-to", default="local", show_default=True,
              help="Where to publish artifact, one of: %s" % list(PUBLISH_MODES.keys()))
@click.option("--no-prompt", is_flag=True, help="Automated mode with no user prompts.")
@click.option("--git-remote", default=DATABRICKS_REMOTE,
              help="Push current branch and docs to this git remote.")
def main(release_version, next_version, publish_to, no_prompt, git_remote):
    interactive = not no_prompt

    time = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    if publish_to not in PUBLISH_MODES:
        modes = list(PUBLISH_MODES.keys())
        prominentPrint("Unknown publish target, --publish-to should be one of: %s." % modes)
        sys.exit(1)

    if not next_version.endswith("SNAPSHOT"):
        next_version += "-SNAPSHOT"

    if not verify("Publishing version: %s\n"
                    "Next version will be: %s\n"
                    "Continue?" % (release_version, next_version), interactive):
        sys.exit(1)

    current_branch = check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if current_branch == "HEAD":
        prominentPrint("Cannot build from detached head state. Please make a branch.")
        sys.exit(1)
    if current_branch != b"master":
        if not verify("You're not on the master branch do you want to continue?",
                      interactive):
            sys.exit(1)

    uncommitted_changes = check_output(["git", "diff", "--stat"])
    if uncommitted_changes != b"":
        prominentPrint("There seem to be uncommitted changes on your current branch. Please commit or "
              "stash them and try again.")
        prominentPrint(uncommitted_changes)
        sys.exit(1)

    if call(["which", "protoc"], stdout=PIPE, stderr=PIPE) != 0:
        prominentPrint("Cannot find protoc, protoc is required to build tensorfames. See README.md.")
        sys.exit(1)


    working_branch = WORKING_BRANCH % (release_version, time)

    release_tag = RELEASE_TAG % release_version
    target_tags = [release_tag]

    existing_tags = check_output(["git", "tag"]).decode().split()
    conflict_tags = list(filter(lambda a: a in existing_tags, target_tags))
    if conflict_tags:
        msg = ("The following tags already exist:\n"
               "    %s\n"
               "Please delete them and try.")
        msg = msg % "\n    ".join(conflict_tags)
        prominentPrint(msg)
        sys.exit(1)

    prominentPrint("Creating working branch for this release.")
    check_call(["git", "checkout", "-b", working_branch])

    prominentPrint("Creating release tag and updating snapshot version.")
    update_version = "release release-version %s next-version %s" % (release_version, next_version)
    check_call(["./build/sbt", update_version])

    prominentPrint("Building and testing with sbt.")
    check_call(["git", "checkout", release_tag])

    publish_target = PUBLISH_MODES[publish_to]
    check_call(["./build/sbt", "clean", publish_target])

    prominentPrint("Updating local branch: %s" % current_branch)
    check_call(["git", "checkout", current_branch])
    check_call(["git", "merge", "--ff", working_branch])
    check_call(["git", "branch", "-d", working_branch])

    prominentPrint("Local branch updated")
    if verify("Would you like to push local branch & version tag to remote: %s?" % git_remote,
              interactive):
        check_call(["git", "push", git_remote, current_branch])
        check_call(["git", "push", git_remote, release_tag])

if __name__ == "__main__":
    main()
