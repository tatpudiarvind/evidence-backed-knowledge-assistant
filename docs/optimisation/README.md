# Optimisation plan

What to do next to make the app faster, cheaper to run, more accurate and easier to operate, in an order that avoids wasted work.

**Ground rules**

- **Measure first.** No speed, memory, size or cost figure has been measured for this app across machines, so this plan states none. Every step below starts by taking a baseline, and a change is kept only if the numbers improve under the same conditions. Don't publish a figure from a run you didn't make.
- **Keep the safety properties.** An optimisation must not weaken workspace isolation, citation checks, abstention on weak evidence, upload limits, or the "browser never talks to the database or a model" boundary. Every change keeps the existing tests and the evaluation agreement check green.
- **One change per branch**, with its before and after recorded in the tracker's verification log.
- **Stay a modular monolith.** Nothing here needs Kafka, microservices or Kubernetes. Add them only after a measurement shows a need.

## 1. What the code does today (the starting point)

These are facts read from the repository, not measurements.

| Area | Today |
| --- | --- |
| Vector search | pgvector with an HNSW index on `document_chunks.embedding` using cosine distance. Results are filtered to the workspace's ready documents and its members |
| Keyword search | A stored `tsvector` column (English) with a GIN index; `websearch_to_tsquery` and `ts_rank` |
| Search modes | `vector` (default), `hybrid`, `hybrid_rerank`. `hybrid_rerank` is unmeasured |
| Embeddings | `sentence-transformers`, loaded on the CPU (`device="cpu"`), in batches (`EMBEDDING_BATCH_SIZE=32`) |
| Indexing | A durable `jobs` table. By default the API process indexes (`INDEXING_RUNNER=embedded`); a separate `worker` runner exists. Text is extracted in a time-limited child process |
| Answers | Retrieve, build a prompt, then call the model (Ollama by default outside Compose, optional OpenAI-compatible adapter). The model call is expected to be the slowest step, but that hasn't been profiled |
| Web app | React 19 and Vite. The document list refreshes itself with a timer (`DocumentLibrary.tsx`). No route or component code splitting was found |
| Rate limits | Counted in the API process's memory and reset on restart |
| Images | Multi-stage Docker builds; the backend's dependencies include PyTorch, which is large |
| Evaluation | A small synthetic set. On the held-out set, `hybrid` tied `vector` on hits (42 of 44) and had a higher mean reciprocal rank (0.8854 against 0.7784), so `vector` stayed the default (D-82). 4 of 61 citations in the answer run didn't state the fact they were attached to |

## 2. Step 0: build the measuring tools (do this first)

Nothing else in this plan is trustworthy without it.

| Task | How | Done when |
| --- | --- | --- |
| Time each stage of a question | The API already logs with a request ID and can serve `/metrics` (`METRICS_ENABLED=true`). Add per-stage timings: embed the question, search, rerank, prompt build, model call, citation check | A single question's log shows where its time went |
| Time each stage of indexing | The same for parse, chunk, embed, store | A document's log shows where its time went |
| A repeatable load script | A small script using HTTPX or k6 against the production-style stack, with a fixed set of questions and uploads | Two runs on the same machine agree closely enough to tell a real change from noise |
| Record the conditions | Machine, CPU, memory, GPU, model and settings, with every result | Every number in the docs has its conditions beside it, as in the evaluation guide |
| Size baselines | Docker image sizes, the built web app's file sizes, the API's memory after startup and while indexing | A baseline table in the tracker |

## 3. Phase A: answer latency

The user waits on this path, so it comes first. Take the stage timings from step 0 and attack the largest stage.

1. **Model call.** Usually the largest cost for a local model. Options, in order of cost:
   - Use a smaller or more heavily quantised model, then re-run the evaluation to check answer quality hasn't dropped.
   - Cut the context sent to the model (`ANSWER_CONTEXT_CHARACTERS`, `RETRIEVAL_TOP_K`) and check recall and citation correctness.
   - Stream the answer to the browser (server-sent events) so the first words appear sooner. This changes perceived speed, not total time. It needs care: citation validation happens on the complete answer, so a streamed answer must be shown as unverified until it is checked.
   - Keep the model loaded between questions (Ollama's keep-alive setting) so the first question after idle doesn't pay the load time.
2. **Question embedding.** Keep the embedding model loaded for the life of the process (check it already is), and consider a small cache for repeated questions. A cache must be keyed by workspace and user where it holds anything derived from documents, and must respect the 3-day retention.
3. **Search.** Check query plans with `EXPLAIN (ANALYZE)` on a realistic corpus. Then tune the HNSW search setting (`hnsw.ef_search`) and the iterative-scan setting that the workspace filter relies on, measuring recall against the evaluation, not by eye. Increasing candidates raises cost; decreasing it can drop true hits.
4. **Reranking.** Measure `hybrid_rerank` for the first time (tracker B-03). Reranking adds a model run for every candidate, so weigh its quality gain against its latency.

**Done when:** the median and the slowest-case question time are recorded before and after on the same machine, and the evaluation's retrieval and citation results haven't dropped.

## 4. Phase B: indexing throughput and memory

1. **Use the GPU or a faster embedder if one is available.** The embedder is pinned to the CPU. Make the device a setting, and compare the batch size against memory. Keep the CPU default.
2. **Tune `EMBEDDING_BATCH_SIZE`** with the stage timings, watching memory.
3. **Separate the worker** (`INDEXING_RUNNER=worker`) so a large upload doesn't compete with question answering for CPU and memory. Compare the API's question latency while indexing, in both modes.
4. **Chunk settings.** Chunk size and overlap change both index size and answer quality. Change them only with an evaluation run behind the change, and re-index afterwards.
5. **Large files.** The limits (`MAX_UPLOAD_BYTES`, `MAX_DOCUMENT_PAGES`, `MAX_DOCUMENT_CHARACTERS`, `PARSE_TIMEOUT_SECONDS`) protect the machine. Revisit them only with a measured reason.
6. **Re-indexing only what changed.** When settings change, indexed documents keep their old chunks. A command that re-indexes selected documents would help; it needs a design for failures part-way.
7. **Several workers.** The job queue is in PostgreSQL. Before running more than one worker, check that claiming a job is safe against two workers taking the same job (a test with two workers).

## 5. Phase C: database

1. **Indexes.** Look at the slow-query data (`pg_stat_statements`) after the load script, and add an index only for a query that shows up. Every extra index slows writes.
2. **HNSW build settings** (`m`, `ef_construction`). Larger values can raise recall and cost build time and memory. Measure with the evaluation.
3. **Vector storage.** Larger corpora may justify smaller vectors (for example half-precision storage) or a smaller embedding model. Both change recall, so they need an evaluation run, and the embedding dimension is part of the schema (a migration and a re-index).
4. **Connection pool.** Check the pool size against the number of API processes and PostgreSQL's connection limit.
5. **Retention and cleanup.** Questions and answers are deleted after 3 days. Check that the cleanup is cheap on a large table, and that deleting a document removes its chunks and vectors promptly.
6. **Maintenance.** After many deletes, check table bloat and the index's health, and decide whether `VACUUM` settings need attention.
7. **Backups.** Document a tested backup and restore (the operations guide has the steps; they haven't been run by the author on a real deployment).

## 6. Phase D: search quality (accuracy is an optimisation too)

1. **Larger, independently reviewed evaluation set.** The sets are small and have one reviewer. This limits every conclusion below. Add questions, add a second reviewer, and report intervals or counts, not just percentages.
2. **Re-decide the default search mode** with the larger set (D-82). `hybrid` improved the ranking order but tied on hits.
3. **Citation correctness.** Some citations don't state the fact they are attached to. Options: a stricter prompt, a check that the cited passage actually contains support for the sentence it backs, dropping or flagging unsupported citations, and measuring again.
4. **Abstention.** Tune `RETRIEVAL_MIN_SIMILARITY` with questions the documents can't answer, measuring both wrongly-answered and wrongly-refused cases, not only one.
5. **Better chunking** that respects headings, tables and page boundaries, evaluated against the current fixed-size chunks.
6. **Query handling.** Question clean-up already exists (`QUESTION_CLEANUP_ENABLED`). Test whether it helps or hurts on the larger set before extending it.
7. **Prompt-injection tests.** Add more hostile documents to the evaluation, because document text is untrusted input.

## 7. Phase E: web app

1. **Measure first**: Lighthouse and the built files' sizes, with the conditions recorded.
2. **Split the code** so the sign-in screen doesn't load code only needed later (React's `lazy` and Vite's dynamic imports), if the sizes justify it.
3. **Polling.** The document list refreshes on a timer. Compare an adaptive interval (fast while a document is processing, slow or stopped otherwise) against the current one, to cut needless requests. Server-sent events are possible, but are more moving parts than the problem may need.
4. **Cache and avoid duplicate requests** with a small data-fetching layer only if the code starts repeating itself. Don't add a library for its own sake.
5. **Accessibility and mobile.** The end-to-end tests run automated accessibility checks. Add a manual keyboard and screen reader pass, and a small-screen pass.

## 8. Phase F: build, images and CI

1. **Image size.** Record the sizes, then look at what the backend image carries. PyTorch is the largest part. A CPU-only PyTorch build can be much smaller than the default one; check it works with the pinned `sentence-transformers` first.
2. **Build cache.** Order Dockerfile layers so the dependency layer is reused, and use the CI build cache where it helps.
3. **CI time.** Record each job's time and look at the slowest. Candidates: caching the embedding model between runs (pinned by revision and checked by hash), and running the independent jobs in parallel (they already are).
4. **Dependencies.** Keep the weekly habit of a dependency audit, and don't add libraries without need. Each one adds audit work (the PyJWT failure showed this).
5. **Startup time.** Measure how long the API takes to be ready, since the model loads at start or first use.

## 9. Phase G: reliability, security and operations

1. **Shared rate limits.** Move them out of process memory (for example into PostgreSQL) before running more than one API process.
2. **Health and metrics.** Add metrics for queue depth, indexing time and failed documents, and write alert rules in the operations guide. Don't claim monitoring that isn't set up.
3. **Failure drills.** Practise: database down, model server down, a document that crashes the parser, a full disk, a restart in the middle of indexing. Record what happened.
4. **Hardening already planned:** HTTPS for any shared deployment, secret handling for `OIDC_CLIENT_SECRET` and `LLM_API_KEY`, and a retention review.
5. **Hosted language model.** If one is ever used, measure latency and cost per question first, keep the daily call limit, and get explicit approval of the vendor, terms and cost. Document text then leaves the machine, which the privacy guide must say.
6. **Cloud.** Choose one cloud only after the local app is stable and a cost check is done. Don't assume a free tier persists. Prefer a managed database and a single container service over always-on extras; avoid Kubernetes, NAT gateways and GPUs; set a billing alert; plan how to tear everything down.

## 10. Suggested order

| Order | Work | Why now |
| --- | --- | --- |
| 1 | Step 0: stage timings, load script, baselines | Everything else depends on it |
| 2 | Phase A: the biggest stage of a question | Users feel it first |
| 3 | Phase D, items 1 and 2: a larger independently reviewed evaluation set | Without it, quality changes can't be judged |
| 4 | Phase B: indexing, with the separate worker | Large uploads affect everyone |
| 5 | Phase C: database tuning, driven by the slow queries found | Only add what the data shows |
| 6 | Phase D, items 3 and 4: citations and abstention | Trust is the product |
| 7 | Phase E and F: web app and images | Smaller gains, easy to measure |
| 8 | Phase G: operations, then cloud only if justified | Depends on real usage |

## 11. How to record each change

For every optimisation, add to the tracker:

1. The question ("is the median question time lower?").
2. The conditions (machine, data, settings).
3. The before and after numbers, from runs you made.
4. The evaluation agreement check result, and the test results.
5. The decision: keep, revert, or defer, and why.

A result that didn't help is still worth recording, so nobody repeats it.

## 12. What this plan doesn't claim

- No number here is a measurement of this app. The 42 of 44, 0.8854, 0.7784 and 4 of 61 figures come from the [evaluation guide](../evaluation/README.md), where their conditions are given.
- The suggestions are hypotheses to test, not known improvements.
- The ideas about PyTorch image size, half-precision vectors and server-sent events haven't been tried in this project.
