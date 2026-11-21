# 300-student capacity test

Tested on 2026-11-13 against https://beyond-the-number-college.vercel.app, deployment `dpl_AGjKBepGRUKCgP2YbB3Uk22e2gtJ`, with Cloudflare D1 storage.

**Result: the tested workflow passed for 300 concurrent simulated students.** All 1,500 assessment requests returned HTTP 200 and passed content checks, without client retries. All 300 students received distinct saved question sets and submitted correct 20/20 results. A direct D1 query independently confirmed 300 attempts, 300 distinct learners, 300 distinct sets, 300 committed grades and 300 correct final results.

| Phase (300 requests each) | Successful | Failed | Median | 95th percentile | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simultaneous test start | 300 | 0 | 5.96 s | 6.42 s | 6.45 s |
| Autosave burst 1 | 300 | 0 | 5.82 s | 6.27 s | 6.30 s |
| Autosave burst 2 | 300 | 0 | 4.99 s | 5.55 s | 5.59 s |
| Autosave burst 3 | 300 | 0 | 5.89 s | 7.24 s | 7.29 s |
| Simultaneous final submission | 300 | 0 | 4.82 s | 5.15 s | 5.22 s |

## Method and scope

Students were synthetic, already enrolled and authenticated. Each student received 20 questions selected from a 60-question bank. Five synchronized bursts tested starting, saving 5, 10 and 20 answers, and final submission. The HTTP/2 load generator used three warmed connections with 100 independent student sessions per connection. Latencies include the test machine's network, Vercel gateway, Cloudflare Worker and D1. This measures concurrent application requests, not 300 separately rendered browser instances.

This does not establish the maximum number of students, certify other class sizes, or test simultaneous registration/login, PDF uploads, exam-long sustained traffic or different network conditions. The test deliberately bypassed bulk account creation by seeding temporary students and hashed sessions; the assessment requests used normal authenticated production endpoints.

An earlier cold HTTP/1 test using 300 separate TLS connections produced 295 successful starts and five connection timeouts, with a 27.47 s 95th percentile. It did not proceed to saves/submission. The gateway was then changed to reuse backend HTTP/2 connections, and the load generator switched to warmed HTTP/2 transport. Because both changed, the improvement cannot be attributed solely to the gateway change. The earlier failure is retained in the baseline report.

The shared backend client rejects backend cookie storage. A dedicated isolation test verifies that it cannot transfer one student's session to another. All 33 Python tests, Cloudflare backend integration checks and frontend checks passed after the pooling change.

## Artifacts and cleanup

- Full results: `artifacts/capacity-300-report.json`.
- Initial run: `artifacts/capacity-300-baseline.json`.
- Reproducible generator: `tests/load_test.py`.

The temporary classroom, quiz, attempts, 300 student accounts, teacher account and sessions were removed after verification. Cleanup used exact generated IDs and did not modify college records. Test session secrets were never printed and their temporary files were removed.
