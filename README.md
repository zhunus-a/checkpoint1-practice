# Checkpoint 1 - practice

The same format as Checkpoint 1 on Tuesday 27 October, with **four practice
faults, one in each block**. None of them is one of the real checkpoint's
faults, but they are found the same way: from the pipeline's log.

## How to use it (about 30 minutes)

1. **Use this template -> Create a new repository**, in your own account,
   public (public repositories get free Actions minutes).
2. Open **Actions**. If there is no run yet, open the **CI** workflow and press
   **Run workflow**. Read the red step, then its first error line.
3. Clone your copy, make a branch, open a pull request into your own `main`.
   Fix one thing, push, read the new run. Repeat.
4. After each fix, fill in that block of the pull request description.
5. Check yourself: copy your pull request description into a file `pr.md`, then
   `python3 checkpoint/mark_cp1.py --pr-body pr.md`.

The walkthrough of the first fault is on the Checkpoint 1 preparation page.
Try on your own before you read it.

## The four blocks - 25 points each

| Block | What must be true |
|---|---|
| **1. The pipeline runs** | the job checks out the code and can run `scripts/test.sh` (executable in Git, Linux line endings) |
| **2. The pipeline tells the truth** | a failing test makes `scripts/test.sh` exit non-zero, so the step goes red |
| **3. The service keeps the contract** | the tests pass: `/healthz` answers 200, `$PORT` is honoured, the server binds `0.0.0.0` |
| **4. The image builds** | the image builds, its name is lowercase, and M3's hygiene holds (non-root `USER`, `.dockerignore`, dependencies before code) |

Each block is worth 15 points for the fix and 10 for its diagnosis. The exact
rules are in `checkpoint/mark_cp1.py`.
