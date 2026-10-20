/**
 * static/app.js - AI Data Insight Builder Frontend Application
 * 
 * 규정된 프론트엔드 콘솔 로깅 태그:
 * [PAGE]    페이지 로드 완료
 * [UPLOAD]  파일 선택 (파일명, 크기)
 * [INSPECT] 진단 요청 시작 / 응답 수신 (행 수, 열 수, 경고 수)
 * [SUGGEST] 제안 요청 시작 / 응답 수신 (제안 개수)
 * [RUN]     도구 실행 시작 (도구명, 기준시점) / 결과 수신
 * [CHART]   차트 렌더 완료 (차트 종류)
 * [EXPLAIN] 해석 요청 시작 (모드) / 응답 수신
 * [ERROR]   오류 발생
 */

document.addEventListener("DOMContentLoaded", () => {
    console.log("[PAGE] 페이지 로드 완료");

    // =========================================================================
    // 전역 상태 변수
    // =========================================================================
    let selectedFile = null;
    let inspectData = null;
    let selectedTool = null;
    let selectedParams = {};
    let lastRunResult = null;
    let currentChartInstance = null;
    let currentExplainMode = "B";
    let lastGeneratedReportText = "";
    let lastGeneratedReportMode = "B";
    let lastUserQuery = "";

    // 12개 분석 도구의 직관적이고 친절한 한글 명칭 매핑
    const TOOL_KOREAN_NAMES = {
        "top_bottom_n": "국가별 순위 비교 분석 (상위·하위 N개국)",
        "compare_one_vs_all": "대한민국 vs 전 세계 벤치마킹 비교",
        "trend_line": "주요국 연도별 시계열 추이 비교 (꺾은선 차트)",
        "describe_numeric": "핵심 기술통계량 산출 (평균·중앙값·사분위수)",
        "group_summary": "대륙·지역 및 소득군별 평균 비교",
        "change_rate": "기간별 변화량 및 성장률 분석",
        "distribution": "수치 구간별 빈도 분포 분석 (히스토그램)",
        "correlation_scatter": "두 지표 상관분석 및 산점도",
        "quality_report": "데이터 품질 진단 리포트 (결측치·중복 점검)",
        "detect_aggregates": "대륙·경제권 집계 그룹 탐지 (왜곡 방지)",
        "year_coverage": "연도별 충실도 분석 (권장 기준시점 탐색)",
        "reshape_wide_to_long": "연도 열 행으로 접기 (롱 포맷 변환)"
    };

    function getToolKoreanName(toolKey) {
        return TOOL_KOREAN_NAMES[toolKey] || toolKey;
    }

    // =========================================================================
    // DOM 엘리먼트 캐싱
    // =========================================================================
    const healthBadge = document.getElementById("health-badge");
    const dropZone = document.getElementById("drop-zone");
    const fileInput = document.getElementById("file-input");
    const selectedFileInfo = document.getElementById("selected-file-info");
    const selectedFileName = document.getElementById("selected-file-name");
    const selectedFileSize = document.getElementById("selected-file-size");
    const btnInspect = document.getElementById("btn-inspect");

    const sectionInspect = document.getElementById("section-inspect");
    const valEncoding = document.getElementById("val-encoding");
    const valSkiprows = document.getElementById("val-skiprows");
    const valRows = document.getElementById("val-rows");
    const valCols = document.getElementById("val-cols");
    const valRecYear = document.getElementById("val-rec-year");
    const valAggregates = document.getElementById("val-aggregates");
    const warningsBox = document.getElementById("warnings-box");
    const warningsList = document.getElementById("warnings-list");
    const previewThead = document.getElementById("preview-thead");
    const previewTbody = document.getElementById("preview-tbody");
    const btnSuggest = document.getElementById("btn-suggest");

    const sectionAsk = document.getElementById("section-ask");
    const askSampleChips = document.getElementById("ask-sample-chips");
    const askForm = document.getElementById("ask-form");
    const inputAskQuery = document.getElementById("input-ask-query");
    const btnSubmitAsk = document.getElementById("btn-submit-ask");
    const askLoading = document.getElementById("ask-loading");
    const askResultBox = document.getElementById("ask-result-box");
    const askToolBadge = document.getElementById("ask-tool-badge");
    const askResultTitle = document.getElementById("ask-result-title");
    const askAnswerContent = document.getElementById("ask-answer-content");
    const btnVisualizeAsk = document.getElementById("btn-visualize-ask");
    let currentAskData = null;

    const sectionSuggest = document.getElementById("section-suggest");
    const suggestionsContainer = document.getElementById("suggestions-container");
    const selectManualTool = document.getElementById("select-manual-tool");
    const btnApplyManualTool = document.getElementById("btn-apply-manual-tool");

    const sectionRun = document.getElementById("section-run");
    const inputRefPeriod = document.getElementById("input-ref-period");
    const checkExcludeAggregates = document.getElementById("check-exclude-aggregates");
    const btnExecuteRun = document.getElementById("btn-execute-run");
    const runMetadataBar = document.getElementById("run-metadata-bar");
    const metaToolName = document.getElementById("meta-tool-name");
    const metaRefPeriod = document.getElementById("meta-ref-period");
    const metaUsedRows = document.getElementById("meta-used-rows");
    const metaExcludedRows = document.getElementById("meta-excluded-rows");
    const metaExclusionReason = document.getElementById("meta-exclusion-reason");
    const chartWrapper = document.getElementById("chart-wrapper");
    const analysisChartCanvas = document.getElementById("analysis-chart");
    const resultTableBox = document.getElementById("result-table-box");
    const resultThead = document.getElementById("result-thead");
    const resultTbody = document.getElementById("result-tbody");
    const cautionBox = document.getElementById("caution-box");
    const cautionText = document.getElementById("caution-text");
    const runActionBar = document.getElementById("run-action-bar");
    const btnProceedExplain = document.getElementById("btn-proceed-explain");
    const selectedToolDisplay = document.getElementById("selected-tool-display");

    const sectionExplain = document.getElementById("section-explain");
    const explainQueryBox = document.getElementById("explain-query-box");
    const explainQueryText = document.getElementById("explain-query-text");
    const tabModeB = document.getElementById("tab-mode-b");
    const tabModeA = document.getElementById("tab-mode-a");
    const btnGenerateExplain = document.getElementById("btn-generate-explain");
    const explainLoading = document.getElementById("explain-loading");
    const reportView = document.getElementById("report-view");
    const reportModeTag = document.getElementById("report-mode-tag");
    const reportQueryBanner = document.getElementById("report-query-banner");
    const reportQueryBannerText = document.getElementById("report-query-banner-text");
    const btnDownloadMarkdown = document.getElementById("btn-download-markdown");
    const reportContent = document.getElementById("report-content");

    const chatSection = document.getElementById("chat-section");
    const quickChipsList = document.getElementById("quick-chips-list");
    const chatMessages = document.getElementById("chat-messages");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const btnChatSend = document.getElementById("btn-chat-send");
    let chatHistory = [];

    // =========================================================================
    // 0. 서버 상태 확인 (GET /health)
    // =========================================================================
    async function checkServerHealth() {
        try {
            const res = await fetch("/health");
            if (!res.ok) throw new Error("서버 응답 오류");
            const data = await res.json();
            if (data.api_key_configured) {
                healthBadge.className = "badge badge-success";
                healthBadge.textContent = `● 정상 동작 중 (${data.model || "Gemini"})`;
            } else {
                healthBadge.className = "badge badge-warning";
                healthBadge.textContent = "⚠️ API Key 미설정 (.env 확인 필요)";
            }
        } catch (err) {
            console.error("[ERROR] 서버 상태 확인 실패:", err);
            healthBadge.className = "badge badge-danger";
            healthBadge.textContent = "● 서버 오프라인";
        }
    }
    checkServerHealth();

    // =========================================================================
    // 1. 파일 선택 및 드래그 앤 드롭
    // =========================================================================
    dropZone.addEventListener("click", () => fileInput.click());

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileSelection(e.target.files[0]);
        }
    });

    function handleFileSelection(file) {
        if (!file.name.toLowerCase().endsWith(".csv")) {
            alert("CSV 형식(.csv)의 파일만 업로드할 수 있습니다.");
            console.warn("[ERROR] 비정상 파일 형식 시도:", file.name);
            return;
        }

        const sizeMB = file.size / (1024 * 1024);
        if (sizeMB > 10) {
            alert("파일 크기가 10MB를 초과했습니다. 더 작은 파일을 선택해주세요.");
            console.warn("[ERROR] 파일 크기 초과:", file.size);
            return;
        }

        selectedFile = file;
        const sizeKB = Math.round(file.size / 1024);
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = `(${sizeKB.toLocaleString()} KB)`;
        selectedFileInfo.classList.remove("hidden");

        console.log(`[UPLOAD] 파일 선택 (파일명: ${file.name}, 크기: ${sizeKB} KB)`);
    }

    // =========================================================================
    // 2. 파일 진단 요청 (POST /inspect)
    // =========================================================================
    btnInspect.addEventListener("click", async () => {
        if (!selectedFile) {
            alert("업로드할 파일을 먼저 선택해주세요.");
            return;
        }

        btnInspect.disabled = true;
        btnInspect.textContent = "진단 분석 중...";
        console.log("[INSPECT] 진단 요청 시작");

        const formData = new FormData();
        formData.append("file", selectedFile);

        try {
            const res = await fetch("/inspect", {
                method: "POST",
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "파일 진단 실패");
            }

            inspectData = data;
            const warningsCount = data.warnings ? data.warnings.length : 0;
            console.log(`[INSPECT] 응답 수신 (행 수: ${data.row_count}, 열 수: ${data.col_count}, 경고 수: ${warningsCount})`);

            // 메트릭 카드 렌더링
            valEncoding.textContent = data.encoding;
            valSkiprows.textContent = `${data.skipped_rows}줄`;
            valRows.textContent = `${data.row_count.toLocaleString()}행`;
            valCols.textContent = `${data.col_count.toLocaleString()}열`;
            valRecYear.textContent = data.recommended_reference_period ? `${data.recommended_reference_period}년` : "전체";
            valAggregates.textContent = data.aggregate_row_candidates ? `${data.aggregate_row_candidates.length}개` : "0개";

            // 경고 목록 렌더링
            if (warningsCount > 0) {
                warningsList.innerHTML = "";
                data.warnings.forEach(w => {
                    const li = document.createElement("li");
                    li.textContent = w;
                    warningsList.appendChild(li);
                });
                warningsBox.classList.remove("hidden");
            } else {
                warningsBox.classList.add("hidden");
            }

            // 10행 미리보기 테이블 렌더링
            renderPreviewTable(data.preview_rows, data.column_names);

            // 진단 섹션 및 자연어 질문 섹션 표시
            sectionInspect.classList.remove("hidden");
            if (sectionAsk) {
                sectionAsk.classList.remove("hidden");
            }
            sectionInspect.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] 진단 오류 발생:", err);
            alert(`진단 오류: ${err.message}`);
        } finally {
            btnInspect.disabled = false;
            btnInspect.textContent = "🔍 파일 진단 시작";
        }
    });

    function renderPreviewTable(rows, columns) {
        previewThead.innerHTML = "";
        previewTbody.innerHTML = "";

        if (!rows || rows.length === 0 || !columns) return;

        // 표시할 상위 12개 열만 선별 (가로 스크롤 과부하 방지)
        const displayCols = columns.slice(0, 15);

        displayCols.forEach(col => {
            const th = document.createElement("th");
            th.textContent = col;
            previewThead.appendChild(th);
        });

        rows.forEach(row => {
            const tr = document.createElement("tr");
            displayCols.forEach(col => {
                const td = document.createElement("td");
                const val = row[col];
                td.textContent = (val !== null && val !== undefined) ? val : "-";
                tr.appendChild(td);
            });
            previewTbody.appendChild(tr);
        });
    }

    // =========================================================================
    // 2-1. 데이터에 자연어로 질문하기 (POST /ask)
    // =========================================================================
    if (askSampleChips) {
        askSampleChips.addEventListener("click", (e) => {
            const btn = e.target.closest("button[data-ask]");
            if (btn) {
                const queryText = btn.dataset.ask;
                inputAskQuery.value = queryText;
                handleAskSubmit(queryText);
            }
        });
    }

    if (askForm) {
        askForm.addEventListener("submit", (e) => {
            e.preventDefault();
            handleAskSubmit(inputAskQuery.value);
        });
    }

    async function handleAskSubmit(queryText) {
        const text = (queryText || "").trim();
        if (!text) {
            alert("질문 내용을 입력해주세요.");
            return;
        }

        btnSubmitAsk.disabled = true;
        askLoading.classList.remove("hidden");
        askResultBox.classList.add("hidden");
        console.log(`[ASK] 자연어 질문 전송: ${text}`);

        try {
            const res = await fetch("/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: text })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "자연어 질의 처리 실패");
            }

            console.log(`[ASK] 응답 수신 완료 (도구: ${data.tool})`);
            currentAskData = data;
            lastUserQuery = text;

            // 답변 카드 렌더링
            askToolBadge.textContent = `도구: ${getToolKoreanName(data.tool)}`;
            askResultTitle.textContent = data.title || "데이터 분석 답변";
            askAnswerContent.innerHTML = renderMarkdown(data.answer);
            askResultBox.classList.remove("hidden");
            askResultBox.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] 자연어 질문 오류:", err);
            alert(`질문 처리 오류: ${err.message}`);
        } finally {
            btnSubmitAsk.disabled = false;
            askLoading.classList.add("hidden");
        }
    }

    if (btnVisualizeAsk) {
        btnVisualizeAsk.addEventListener("click", () => {
            if (!currentAskData || !currentAskData.run_result) {
                alert("시각화할 분석 결과가 없습니다. 먼저 질문을 실행해주세요.");
                return;
            }

            const r = currentAskData.run_result;
            selectedTool = currentAskData.tool;
            selectedParams = currentAskData.params || {};
            lastRunResult = r;
            lastUserQuery = currentAskData.query || lastUserQuery;

            if (selectedToolDisplay) {
                selectedToolDisplay.textContent = getToolKoreanName(selectedTool);
                selectedToolDisplay.title = selectedTool;
            }
            if (inputRefPeriod) {
                inputRefPeriod.value = r.reference_period || selectedParams.reference_period || "2024";
            }

            // 메타데이터 바 렌더링
            metaToolName.textContent = `도구: ${getToolKoreanName(r.tool)}`;
            metaRefPeriod.textContent = `기준: ${r.reference_period || "전체"}`;
            metaUsedRows.textContent = `사용: ${r.used_rows_count.toLocaleString()}개 행`;
            metaExcludedRows.textContent = `제외: ${r.excluded_rows_count.toLocaleString()}개 행`;
            runMetadataBar.classList.remove("hidden");

            if (r.exclusion_reason) {
                metaExclusionReason.textContent = `제외 사유: ${r.exclusion_reason}`;
                metaExclusionReason.classList.remove("hidden");
            } else {
                metaExclusionReason.classList.add("hidden");
            }

            // Chart.js 차트 렌더링
            try {
                if (r.chart) {
                    renderChart(r.chart);
                    chartWrapper.classList.remove("hidden");
                } else {
                    chartWrapper.classList.add("hidden");
                }
            } catch (ce) {
                console.warn("[WARN] 차트 렌더링 실패:", ce);
            }

            // 수치 테이블 렌더링
            try {
                renderResultTable(r.data);
                resultTableBox.classList.remove("hidden");
            } catch (te) {
                console.warn("[WARN] 테이블 렌더링 실패:", te);
            }

            // 주의사항 렌더링
            if (r.caution) {
                cautionText.textContent = r.caution;
                cautionBox.classList.remove("hidden");
            } else {
                cautionBox.classList.add("hidden");
            }

            // 4단계 액션 바 및 섹션 노출
            if (runActionBar) {
                runActionBar.classList.remove("hidden");
            }
            sectionRun.classList.remove("hidden");
            sectionRun.scrollIntoView({ behavior: "smooth" });
        });
    }

    // =========================================================================
    // 3. AI 분석 제안 요청 (POST /suggest)
    // =========================================================================
    btnSuggest.addEventListener("click", async () => {
        btnSuggest.disabled = true;
        btnSuggest.textContent = "Gemini가 분석 제안을 고민하는 중...";
        console.log("[SUGGEST] 제안 요청 시작");

        try {
            const res = await fetch("/suggest", { method: "POST" });
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.error || "제안 요청 실패");
            }

            const suggestions = data.suggestions || [];
            console.log(`[SUGGEST] 제안 응답 수신 (제안 개수: ${suggestions.length})`);

            renderSuggestions(suggestions);
            sectionSuggest.classList.remove("hidden");
            sectionSuggest.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] 제안 오류 발생:", err);
            alert(`AI 제안 오류: ${err.message}`);
        } finally {
            btnSuggest.disabled = false;
            btnSuggest.textContent = "✨ Gemini에게 적합한 분석 도구 제안받기";
        }
    });

    function renderSuggestions(suggestions) {
        suggestionsContainer.innerHTML = "";

        if (suggestions.length === 0) {
            suggestionsContainer.innerHTML = "<p class='text-muted'>추천된 제안이 없습니다. 아래 수동 선택을 이용해주세요.</p>";
            return;
        }

        suggestions.forEach((sug, idx) => {
            const card = document.createElement("div");
            card.className = "suggestion-card";
            card.innerHTML = `
                <div>
                    <div class="card-header-row">
                        <span class="tool-tag">${escapeHtml(getToolKoreanName(sug.tool))}</span>
                        <span class="ref-tag">기준: ${sug.reference_period || "전체"}</span>
                    </div>
                    <p class="card-why">${escapeHtml(sug.why)}</p>
                </div>
                <div class="card-caution">
                    <strong>⚠️ 주의:</strong> ${escapeHtml(sug.caution)}
                </div>
            `;

            card.addEventListener("click", () => {
                document.querySelectorAll(".suggestion-card").forEach(c => c.classList.remove("selected"));
                card.classList.add("selected");
                selectToolForRun(sug.tool, sug.params || {}, sug.reference_period);
            });

            suggestionsContainer.appendChild(card);
        });
    }

    btnApplyManualTool.addEventListener("click", () => {
        const tool = selectManualTool.value;
        if (!tool) {
            alert("도구를 선택해주세요.");
            return;
        }
        const defaultRef = (inspectData && inspectData.recommended_reference_period) ? inspectData.recommended_reference_period : "2024";
        selectToolForRun(tool, { reference_period: defaultRef }, defaultRef);
    });

    function selectToolForRun(tool, params, refPeriod) {
        selectedTool = tool;
        selectedParams = params || {};

        if (selectedToolDisplay) {
            selectedToolDisplay.textContent = getToolKoreanName(tool);
            selectedToolDisplay.title = tool;
        }

        const recYear = (inspectData && inspectData.recommended_reference_period) ? inspectData.recommended_reference_period : "2024";
        const targetRef = refPeriod || selectedParams.reference_period || recYear;

        inputRefPeriod.value = targetRef;
        selectedParams.reference_period = targetRef;

        sectionRun.classList.remove("hidden");
        sectionRun.scrollIntoView({ behavior: "smooth" });

        // 분석 도구 선택 시 자동으로 Pandas 계산 즉시 실행
        executeRunAnalysis();
    }

    // =========================================================================
    // 4. 도구 실행 및 시각화 (POST /run)
    // =========================================================================
    async function executeRunAnalysis() {
        if (!selectedTool) {
            alert("실행할 분석 도구를 먼저 선택해주세요.");
            return;
        }

        const refPeriodVal = inputRefPeriod.value.trim();
        const excludeAggregatesVal = checkExcludeAggregates.checked;

        selectedParams.reference_period = refPeriodVal;
        selectedParams.exclude_aggregates = excludeAggregatesVal;

        btnExecuteRun.disabled = true;
        btnExecuteRun.textContent = "Pandas 계산 실행 중...";
        console.log(`[RUN] 도구 실행 시작 (도구명: ${selectedTool}, 기준시점: ${refPeriodVal})`);

        try {
            const res = await fetch("/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    tool: selectedTool,
                    params: selectedParams
                })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "분석 실행 실패");
            }

            lastRunResult = data.result;
            console.log("[RUN] 결과 수신 완료");

            // 메타데이터 바 렌더링
            metaToolName.textContent = `도구: ${getToolKoreanName(lastRunResult.tool)}`;
            metaRefPeriod.textContent = `기준: ${lastRunResult.reference_period || "전체"}`;
            metaUsedRows.textContent = `사용: ${lastRunResult.used_rows_count.toLocaleString()}개 행`;
            metaExcludedRows.textContent = `제외: ${lastRunResult.excluded_rows_count.toLocaleString()}개 행`;
            runMetadataBar.classList.remove("hidden");

            if (lastRunResult.exclusion_reason) {
                metaExclusionReason.textContent = `제외 사유: ${lastRunResult.exclusion_reason}`;
                metaExclusionReason.classList.remove("hidden");
            } else {
                metaExclusionReason.classList.add("hidden");
            }

            // Chart.js 차트 렌더링
            try {
                if (lastRunResult.chart) {
                    renderChart(lastRunResult.chart);
                    chartWrapper.classList.remove("hidden");
                } else {
                    chartWrapper.classList.add("hidden");
                    if (currentChartInstance) {
                        currentChartInstance.destroy();
                        currentChartInstance = null;
                    }
                }
            } catch (chartErr) {
                console.warn("[WARN] 차트 렌더링 오류 (무시 가능):", chartErr);
                chartWrapper.classList.add("hidden");
            }

            // 수치 테이블 렌더링
            try {
                renderResultTable(lastRunResult.data);
                resultTableBox.classList.remove("hidden");
            } catch (tableErr) {
                console.warn("[WARN] 수치 테이블 렌더링 오류 (무시 가능):", tableErr);
            }

            // 주의사항 박스 렌더링
            if (lastRunResult.caution) {
                cautionText.textContent = lastRunResult.caution;
                cautionBox.classList.remove("hidden");
            } else {
                cautionBox.classList.add("hidden");
            }

            // 계산이 성공적으로 완료되었으므로 보고서 작성 버튼 영역 노출
            if (runActionBar) {
                runActionBar.classList.remove("hidden");
            }

            btnProceedExplain.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] 도구 실행 실패:", err);
            alert(`도구 실행 오류: ${err.message}`);
        } finally {
            btnExecuteRun.disabled = false;
            btnExecuteRun.textContent = "▶️ Pandas로 실제 계산 실행";
        }
    }

    btnExecuteRun.addEventListener("click", () => {
        executeRunAnalysis();
    });

    function renderChart(chartConfig) {
        if (currentChartInstance) {
            currentChartInstance.destroy();
        }

        const ctx = analysisChartCanvas.getContext("2d");
        const chartType = chartConfig.type || "bar";

        const options = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: !!chartConfig.title,
                    text: chartConfig.title || "",
                    font: { size: 16, weight: "bold" },
                    padding: { bottom: 16 }
                },
                legend: {
                    display: chartType !== "bar" || (chartConfig.datasets && chartConfig.datasets.length > 1)
                }
            }
        };

        if (chartConfig.indexAxis === "y") {
            options.indexAxis = "y";
        }

        currentChartInstance = new Chart(ctx, {
            type: chartType,
            data: {
                labels: chartConfig.labels || [],
                datasets: chartConfig.datasets || []
            },
            options: options
        });

        console.log(`[CHART] 차트 렌더 완료 (차트 종류: ${chartType})`);
    }

    function renderResultTable(dataObj) {
        resultThead.innerHTML = "";
        resultTbody.innerHTML = "";

        if (!dataObj) return;

        // top_n / bottom_n 리스트인 경우
        if (dataObj.top_n && Array.isArray(dataObj.top_n)) {
            resultThead.innerHTML = "<tr><th>순위</th><th>항목명</th><th>수치 (%)</th></tr>";
            dataObj.top_n.forEach(item => {
                const tr = document.createElement("tr");
                if (item.is_korea) {
                    tr.style.backgroundColor = "#fef2f2";
                    tr.innerHTML = `<td><span class="badge badge-danger">${item.rank}위</span></td><td><strong>${escapeHtml(item.label)} 🇰🇷 (대한민국)</strong></td><td><strong style="color:#dc2626;">${item.value}%</strong></td>`;
                } else {
                    tr.innerHTML = `<td>${item.rank}위</td><td><strong>${escapeHtml(item.label)}</strong></td><td>${item.value}%</td>`;
                }
                resultTbody.appendChild(tr);
            });
            return;
        }

        // group_summary 그룹 목록인 경우
        if (dataObj.groups && Array.isArray(dataObj.groups)) {
            resultThead.innerHTML = "<tr><th>그룹명</th><th>평균 수치 (%)</th><th>국가 수</th></tr>";
            dataObj.groups.forEach(g => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td><strong>${escapeHtml(g.group)}</strong></td><td>${g.value}%</td><td>${g.count}개국</td>`;
                resultTbody.appendChild(tr);
            });
            return;
        }

        // change_rate 목록인 경우
        if (dataObj.top_growth && Array.isArray(dataObj.top_growth)) {
            resultThead.innerHTML = "<tr><th>순위</th><th>국가명</th><th>시작 시점</th><th>종료 시점</th><th>증가량 (%p)</th><th>성장률 (%)</th></tr>";
            dataObj.top_growth.forEach(g => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td>${g.rank}</td><td><strong>${escapeHtml(g.label)}</strong></td><td>${g.start_val}%</td><td>${g.end_val}%</td><td><strong>+${g.diff_points}%p</strong></td><td>${g.pct_change ? g.pct_change + "%" : "-"}</td>`;
                resultTbody.appendChild(tr);
            });
            return;
        }

        // distribution 구간 빈도 분포인 경우
        if (dataObj.distribution && Array.isArray(dataObj.distribution)) {
            resultThead.innerHTML = "<tr><th>수치 구간</th><th>국가/항목 수</th><th>비율 (%)</th></tr>";
            dataObj.distribution.forEach(d => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td><strong>${escapeHtml(d.range)}</strong></td><td>${d.count}개국</td><td>${d.percentage}%</td>`;
                resultTbody.appendChild(tr);
            });
            return;
        }

        // detect_aggregates 집계 후보 목록인 경우
        if (dataObj.aggregate_candidates && Array.isArray(dataObj.aggregate_candidates)) {
            resultThead.innerHTML = "<tr><th>순번</th><th>집계 항목명</th><th>매칭 키워드</th></tr>";
            dataObj.aggregate_candidates.slice(0, 15).forEach((c, idx) => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td>${idx + 1}</td><td><strong>${escapeHtml(c.label)}</strong></td><td><code>${escapeHtml(c.matched_keyword)}</code></td>`;
                resultTbody.appendChild(tr);
            });
            return;
        }

        // quality_report 열별 품질 목록인 경우
        if (dataObj.columns_quality && Array.isArray(dataObj.columns_quality)) {
            resultThead.innerHTML = "<tr><th>열 이름</th><th>데이터 타입</th><th>결측치 수</th><th>결측률 (%)</th></tr>";
            dataObj.columns_quality.slice(0, 15).forEach(c => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td><strong>${escapeHtml(c.column)}</strong></td><td>${c.dtype}</td><td>${c.missing_count}개</td><td>${c.missing_percentage}%</td>`;
                resultTbody.appendChild(tr);
            });
            return;
        }

        // year_coverage 연도별 충실도 목록인 경우
        if (dataObj.coverage_by_year && Array.isArray(dataObj.coverage_by_year)) {
            resultThead.innerHTML = "<tr><th>연도</th><th>유효 데이터 수</th><th>충실도 비율 (%)</th></tr>";
            dataObj.coverage_by_year.slice(-15).reverse().forEach(c => {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td><strong>${c.year}년</strong></td><td>${c.valid_count}건</td><td>${c.valid_percentage}%</td>`;
                resultTbody.appendChild(tr);
            });
            return;
        }

        // reshape_wide_to_long 미리보기 행인 경우
        if (dataObj.preview_50_rows && Array.isArray(dataObj.preview_50_rows)) {
            const firstRow = dataObj.preview_50_rows[0] || {};
            const headers = Object.keys(firstRow);
            resultThead.innerHTML = `<tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr>`;
            dataObj.preview_50_rows.slice(0, 10).forEach(r => {
                const tr = document.createElement("tr");
                tr.innerHTML = headers.map(h => `<td>${escapeHtml(String(r[h] ?? ""))}</td>`).join("");
                resultTbody.appendChild(tr);
            });
            return;
        }

        // 일반 키-값 객체인 경우 (describe_numeric, compare_one_vs_all 등)
        resultThead.innerHTML = "<tr><th>항목</th><th>값</th></tr>";
        for (const [k, v] of Object.entries(dataObj)) {
            if (typeof v === "object" && v !== null && !Array.isArray(v)) {
                for (const [subK, subV] of Object.entries(v)) {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `<td>${escapeHtml(k)} > ${escapeHtml(subK)}</td><td><strong>${subV}</strong></td>`;
                    resultTbody.appendChild(tr);
                }
            } else if (!Array.isArray(v)) {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td>${escapeHtml(k)}</td><td><strong>${v}</strong></td>`;
                resultTbody.appendChild(tr);
            }
        }
    }

    // =========================================================================
    // 5. AI 인사이트 해석 보고서 (POST /explain)
    // =========================================================================
    function updateExplainQueryUI() {
        const queryToDisplay = (lastRunResult && lastRunResult.user_query) || lastUserQuery || "";
        if (queryToDisplay && explainQueryBox && explainQueryText) {
            explainQueryText.textContent = `"${queryToDisplay}"`;
            explainQueryBox.classList.remove("hidden");
        } else if (explainQueryBox) {
            explainQueryBox.classList.add("hidden");
        }
    }

    btnProceedExplain.addEventListener("click", () => {
        if (!lastRunResult) {
            alert("먼저 4단계에서 'Pandas로 실제 계산 실행'을 완료해주세요.");
            sectionRun.scrollIntoView({ behavior: "smooth" });
            return;
        }
        updateExplainQueryUI();
        sectionExplain.classList.remove("hidden");
        sectionExplain.scrollIntoView({ behavior: "smooth" });
    });

    tabModeB.addEventListener("click", () => {
        tabModeB.classList.add("active");
        tabModeA.classList.remove("active");
        currentExplainMode = "B";
    });

    tabModeA.addEventListener("click", () => {
        tabModeA.classList.add("active");
        tabModeB.classList.remove("active");
        currentExplainMode = "A";
    });

    btnGenerateExplain.addEventListener("click", async () => {
        if (currentExplainMode === "B" && !lastRunResult) {
            alert("분석 도구 계산 결과가 없습니다. 먼저 4단계에서 'Pandas로 실제 계산 실행'을 완료해주세요.");
            sectionRun.scrollIntoView({ behavior: "smooth" });
            return;
        }

        btnGenerateExplain.disabled = true;
        explainLoading.classList.remove("hidden");
        reportView.classList.add("hidden");

        const queryToSend = (lastRunResult && lastRunResult.user_query) || lastUserQuery || "";
        console.log(`[EXPLAIN] 해석 요청 시작 (모드: ${currentExplainMode}, 연계 질문: "${queryToSend}")`);

        try {
            const res = await fetch("/explain", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    mode: currentExplainMode,
                    run_result: lastRunResult,
                    user_query: queryToSend
                })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "해석 생성 실패");
            }

            console.log(`[EXPLAIN] 해석 응답 수신 (모드: ${data.mode})`);

            if (data.mode === "B") {
                reportModeTag.className = "badge badge-success";
                reportModeTag.textContent = "🌟 모드 B 정식 보고서 (Pandas 계산 결과 기반 8대 규칙 적용)";
            } else {
                reportModeTag.className = "badge badge-warning";
                reportModeTag.textContent = "⚠️ 모드 A 비교용 보고서 (계산 결과 미반영 - 체험용)";
            }

            // 연계된 질문 배너 노출
            const queryUsed = data.user_query || queryToSend;
            if (queryUsed && reportQueryBanner && reportQueryBannerText) {
                reportQueryBannerText.textContent = `"${queryUsed}"`;
                reportQueryBanner.classList.remove("hidden");
            } else if (reportQueryBanner) {
                reportQueryBanner.classList.add("hidden");
            }

            lastGeneratedReportText = data.explanation;
            lastGeneratedReportMode = data.mode;

            reportContent.innerHTML = renderMarkdown(data.explanation);
            reportView.classList.remove("hidden");

            // 후속 질의응답(Q&A) 대화창 활성화 및 말풍선 추천 질문 칩 초기화
            if (chatSection) {
                chatSection.classList.remove("hidden");
                chatHistory = [];
                renderQuickChips([
                    "중학생도 이해할 수 있게 쉽게 설명해줘.",
                    "이 결과에서 초보자가 주의해야 할 해석상 함정은 뭐야?",
                    "이 통계 결과가 현실 정책이나 비즈니스에 주는 시사점은 뭐야?"
                ]);
            }

            reportView.scrollIntoView({ behavior: "smooth" });

        } catch (err) {
            console.error("[ERROR] 해석 보고서 생성 오류:", err);
            alert(`해석 생성 오류: ${err.message}`);
        } finally {
            btnGenerateExplain.disabled = false;
            explainLoading.classList.add("hidden");
        }
    });

    // =========================================================================
    // 5-1. 최종 분석 보고서 및 대화 이력 마크다운(.md) 다운로드
    // =========================================================================
    if (btnDownloadMarkdown) {
        btnDownloadMarkdown.addEventListener("click", () => {
            if (!lastGeneratedReportText) {
                alert("다운로드할 분석 보고서 내용이 없습니다. 먼저 보고서를 생성해주세요.");
                return;
            }

            const now = new Date();
            const dateStr = now.getFullYear() + "-" +
                String(now.getMonth() + 1).padStart(2, "0") + "-" +
                String(now.getDate()).padStart(2, "0") + " " +
                String(now.getHours()).padStart(2, "0") + ":" +
                String(now.getMinutes()).padStart(2, "0") + ":" +
                String(now.getSeconds()).padStart(2, "0");

            const modeTitle = lastGeneratedReportMode === "B"
                ? "모드 B (Pandas 계산 결과 기반 정식 보고서)"
                : "모드 A (비교용 개요 보고서)";

            const toolKey = (lastRunResult && lastRunResult.tool) ? lastRunResult.tool : (selectedTool || "analysis");
            const toolKor = getToolKoreanName(toolKey);
            const refPeriod = (lastRunResult && lastRunResult.reference_period) ? lastRunResult.reference_period : (inputRefPeriod ? inputRefPeriod.value : "전체");
            const queryForMd = (lastRunResult && lastRunResult.user_query) || lastUserQuery || "";

            let md = `# 📊 AI Data Insight Builder 데이터 분석 보고서\n\n`;
            md += `> **생성 일시**: ${dateStr}  \n`;
            md += `> **보고서 모드**: ${modeTitle}  \n`;
            if (queryForMd) {
                md += `> **연계된 사용자 질문**: ${queryForMd}  \n`;
            }
            md += `> **적용 분석 도구**: ${toolKor} (\`${toolKey}\`)  \n`;
            md += `> **분석 기준 시점**: ${refPeriod}  \n`;

            if (lastRunResult && lastRunResult.used_rows_count !== undefined) {
                md += `> **분석 데이터 규모**: 유효 행 ${lastRunResult.used_rows_count.toLocaleString()}개 / 제외 행 ${lastRunResult.excluded_rows_count.toLocaleString()}개  \n`;
            }
            if (lastRunResult && lastRunResult.exclusion_reason) {
                md += `> **집계 그룹 제외 사유**: ${lastRunResult.exclusion_reason}  \n`;
            }

            md += `\n---\n\n`;
            md += `## 📝 AI 분석 종합 보고서\n\n`;
            md += `${lastGeneratedReportText.trim()}\n\n`;

            // 후속 질의응답(Q&A) 대화 내역이 있는 경우 함께 포함
            if (chatHistory && chatHistory.length > 0) {
                md += `---\n\n`;
                md += `## 💬 보고서 후속 질의응답 (Q&A 대화 이력)\n\n`;
                let qIdx = 1;
                chatHistory.forEach(item => {
                    if (item.role === "user") {
                        md += `### Q${qIdx}. ${item.content}\n\n`;
                        qIdx++;
                    } else if (item.role === "assistant") {
                        md += `**🤖 AI 튜터 답변:**\n\n${item.content.trim()}\n\n`;
                    }
                });
            }

            md += `---\n`;
            md += `*본 보고서는 AI Data Insight Builder에 의해 자동 생성되었으며, 모든 통계 수치는 Python Pandas에 의해 정확하게 산출되었습니다.*\n`;

            // UTF-8 BOM(\uFEFF)을 포함하여 텍스트 파일 저장 (한글 깨짐 방지)
            const blob = new Blob(["\uFEFF" + md], { type: "text/markdown;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            const dateIso = now.toISOString().slice(0, 10);
            a.download = `AI_데이터분석보고서_${toolKey}_${dateIso}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            console.log(`[PAGE] 마크다운 보고서 다운로드 완료 (${a.download})`);
        });
    }

    // =========================================================================
    // 6. 보고서 후속 질의응답 (POST /chat)
    // =========================================================================
    function renderQuickChips(questions) {
        if (!quickChipsList) return;
        quickChipsList.innerHTML = "";

        // "중학생도 이해할 수 있게 쉽게 설명해줘."는 항상 말풍선 첫 번째로 고정/포함
        const easyPrompt = "중학생도 이해할 수 있게 쉽게 설명해줘.";
        const uniqueQuestions = [easyPrompt];
        (questions || []).forEach(q => {
            if (q && q !== easyPrompt && !uniqueQuestions.includes(q)) {
                uniqueQuestions.push(q);
            }
        });

        uniqueQuestions.slice(0, 4).forEach((q, idx) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = idx === 0 ? "chat-chip chip-highlight" : "chat-chip";
            btn.textContent = idx === 0 ? `✨ ${q}` : `💡 ${q}`;
            btn.addEventListener("click", () => {
                sendChatMessage(q);
            });
            quickChipsList.appendChild(btn);
        });
    }

    async function sendChatMessage(messageText) {
        const text = (messageText || "").trim();
        if (!text) return;

        chatInput.value = "";
        btnChatSend.disabled = true;
        console.log(`[CHAT] 사용자 질문 전송: ${text}`);

        // 1. 사용자 말풍선 추가
        const userMsgEl = document.createElement("div");
        userMsgEl.className = "chat-msg chat-msg-user";
        userMsgEl.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
        chatMessages.appendChild(userMsgEl);

        // 2. AI 로딩 인디케이터 말풍선 추가
        const loadingMsgEl = document.createElement("div");
        loadingMsgEl.className = "chat-msg chat-msg-ai";
        loadingMsgEl.innerHTML = `
            <div class="chat-avatar">🤖</div>
            <div class="chat-bubble chat-msg-loading">
                <div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0;"></div>
                답변을 생성하고 있습니다...
            </div>
        `;
        chatMessages.appendChild(loadingMsgEl);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        try {
            const res = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: text,
                    history: chatHistory
                })
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || "답변 생성 실패");
            }

            console.log("[CHAT] AI 답변 수신 완료");

            // AI 답변 렌더링
            loadingMsgEl.innerHTML = `
                <div class="chat-avatar">🤖</div>
                <div class="chat-bubble">${renderMarkdown(data.reply)}</div>
            `;

            // 대화 이력 저장
            chatHistory.push(
                { role: "user", content: text },
                { role: "assistant", content: data.reply }
            );

            // 동적 추천 후속 질문 말풍선 칩 갱신
            if (data.suggested_questions && data.suggested_questions.length > 0) {
                renderQuickChips(data.suggested_questions);
            }

        } catch (err) {
            console.error("[ERROR] 채팅 전송 실패:", err);
            loadingMsgEl.innerHTML = `
                <div class="chat-avatar">🤖</div>
                <div class="chat-bubble" style="color:#ef4444;">
                    ⚠️ 답변 생성 중 오류가 발생했습니다: ${escapeHtml(err.message)}
                </div>
            `;
        } finally {
            btnChatSend.disabled = false;
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    if (chatForm) {
        chatForm.addEventListener("submit", (e) => {
            e.preventDefault();
            sendChatMessage(chatInput.value);
        });
    }

    // =========================================================================
    // 유틸리티 함수: 가독성 높은 블록 단위 마크다운 렌더러
    // =========================================================================
    function renderMarkdown(mdText) {
        if (!mdText) return "";

        // 1. 줄바꿈 정규화
        let text = mdText.replace(/\r\n/g, "\n");

        // 2. HTML 특수문자 이스케이프
        text = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // 3. 인라인 서식 (코드, 볼드, 이탤릭)
        text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
        text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");

        // 4. 줄 단위 블록 파싱 (제목, 인용구, 목록, 구분선, 문단)
        const lines = text.split("\n");
        let result = [];
        let inUl = false;
        let inOl = false;
        let inBlockquote = false;
        let currentParagraph = [];

        function flushParagraph() {
            if (currentParagraph.length > 0) {
                result.push(`<p>${currentParagraph.join("<br>")}</p>`);
                currentParagraph = [];
            }
        }

        function closeLists() {
            if (inUl) {
                result.push("</ul>");
                inUl = false;
            }
            if (inOl) {
                result.push("</ol>");
                inOl = false;
            }
        }

        function closeBlockquote() {
            if (inBlockquote) {
                result.push("</blockquote>");
                inBlockquote = false;
            }
        }

        for (let i = 0; i < lines.length; i++) {
            let line = lines[i].trim();

            // 빈 줄 -> 문단 및 리스트 종료
            if (!line) {
                flushParagraph();
                closeLists();
                closeBlockquote();
                continue;
            }

            // 제목 (H1 ~ H4)
            if (line.startsWith("#### ")) {
                flushParagraph();
                closeLists();
                closeBlockquote();
                result.push(`<h4>${line.slice(5)}</h4>`);
                continue;
            }
            if (line.startsWith("### ")) {
                flushParagraph();
                closeLists();
                closeBlockquote();
                result.push(`<h3>${line.slice(4)}</h3>`);
                continue;
            }
            if (line.startsWith("## ")) {
                flushParagraph();
                closeLists();
                closeBlockquote();
                result.push(`<h2>${line.slice(3)}</h2>`);
                continue;
            }
            if (line.startsWith("# ")) {
                flushParagraph();
                closeLists();
                closeBlockquote();
                result.push(`<h1>${line.slice(2)}</h1>`);
                continue;
            }

            // 인용구 (> )
            if (line.startsWith("&gt; ") || line.startsWith("> ")) {
                flushParagraph();
                closeLists();
                const quoteContent = line.replace(/^(&gt;|>)\s*/, "");
                if (!inBlockquote) {
                    result.push("<blockquote>");
                    inBlockquote = true;
                }
                result.push(`<p>${quoteContent}</p>`);
                continue;
            } else {
                closeBlockquote();
            }

            // 구분선 (--- 또는 ***)
            if (/^(\-{3,}|\*{3,})$/.test(line)) {
                flushParagraph();
                closeLists();
                result.push("<hr class='content-divider'>");
                continue;
            }

            // 글머리 기호 목록 (- 또는 *)
            if (line.startsWith("- ") || line.startsWith("* ")) {
                flushParagraph();
                if (inOl) {
                    result.push("</ol>");
                    inOl = false;
                }
                if (!inUl) {
                    result.push("<ul>");
                    inUl = true;
                }
                result.push(`<li>${line.slice(2)}</li>`);
                continue;
            }

            // 번호 매기기 목록 (1. , 2. 등)
            const olMatch = line.match(/^(\d+)\.\s+(.*)$/);
            if (olMatch) {
                flushParagraph();
                if (inUl) {
                    result.push("</ul>");
                    inUl = false;
                }
                if (!inOl) {
                    result.push("<ol>");
                    inOl = true;
                }
                result.push(`<li>${olMatch[2]}</li>`);
                continue;
            }

            // 일반 텍스트 (문단 누적)
            closeLists();
            currentParagraph.push(line);
        }

        flushParagraph();
        closeLists();
        closeBlockquote();

        return result.join("\n");
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
