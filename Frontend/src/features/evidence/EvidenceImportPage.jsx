import { useMemo, useState } from "react";

import { tbmApi } from "@/api/tbm";
import { getApiErrorMessage } from "@/api/client";
import "./evidence.css";

const SOURCE_OPTIONS = [
  { value: "auto", label: "自动识别" },
  { value: "tsp", label: "TSP" },
  { value: "sonic", label: "HSP" },
  { value: "sketch", label: "素描" },
];

const DEFAULT_PATH = "G:\\我的云端硬盘\\TBM9\\TSP\\新超前地质预报\\pdf";

export default function EvidenceImportPage() {
  const [pathsText, setPathsText] = useState(DEFAULT_PATH);
  const [sourceType, setSourceType] = useState("auto");
  const [dryRun, setDryRun] = useState(true);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [recursive, setRecursive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const paths = useMemo(
    () =>
      pathsText
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    [pathsText],
  );

  const sourceLabel =
    SOURCE_OPTIONS.find((item) => item.value === sourceType)?.label || "自动识别";
  const canSubmit = paths.length > 0 && !loading;

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await tbmApi.importEvidence({
        paths,
        source_type: sourceType === "auto" ? null : sourceType,
        dry_run: dryRun,
        replace_existing: replaceExisting,
        recursive,
      });
      setResult(res.data || {});
    } catch (err) {
      console.error("Evidence import failed", err);
      setError(getApiErrorMessage(err, "导入请求失败，请确认后端服务已启动。"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="evidence-console">
      <header className="evidence-console__header">
        <div>
          <div className="evidence-console__eyebrow">Geology Evidence Console</div>
          <h2>地质证据库</h2>
        </div>
        <div className="evidence-console__status">
          <StatusPill label={dryRun ? "模拟" : "写入"} tone={dryRun ? "blue" : "green"} />
          <StatusPill label={sourceLabel} tone="slate" />
        </div>
      </header>

      <div className="evidence-console__body">
        <form
          className="evidence-form"
          onSubmit={(event) => {
            event.preventDefault();
            handleSubmit();
          }}
        >
          <div className="evidence-form__group">
            <label htmlFor="evidence-paths">PDF 路径</label>
            <textarea
              id="evidence-paths"
              value={pathsText}
              onChange={(event) => setPathsText(event.target.value)}
              spellCheck={false}
            />
          </div>

          <div className="evidence-form__row">
            <div className="evidence-form__group">
              <label>资料类型</label>
              <div className="evidence-segmented">
                {SOURCE_OPTIONS.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={sourceType === item.value ? "is-active" : ""}
                    onClick={() => setSourceType(item.value)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="evidence-form__group">
              <label>执行模式</label>
              <div className="evidence-segmented evidence-segmented--two">
                <button
                  type="button"
                  className={dryRun ? "is-active" : ""}
                  onClick={() => setDryRun(true)}
                >
                  预检
                </button>
                <button
                  type="button"
                  className={!dryRun ? "is-active is-write" : ""}
                  onClick={() => setDryRun(false)}
                >
                  入库
                </button>
              </div>
            </div>
          </div>

          <div className="evidence-switches">
            <Switch checked={replaceExisting} onChange={setReplaceExisting} label="覆盖同 ID 记录" />
            <Switch checked={recursive} onChange={setRecursive} label="递归目录" />
          </div>

          <button className="evidence-submit" type="submit" disabled={!canSubmit}>
            {loading ? "处理中..." : dryRun ? "运行预检" : "写入证据库"}
          </button>
        </form>

        <ImportResult result={result} error={error} pathCount={paths.length} />
      </div>
    </section>
  );
}

function ImportResult({ result, error, pathCount }) {
  if (error) {
    return (
      <aside className="evidence-result evidence-result--error">
        <h3>请求失败</h3>
        <p>{error}</p>
      </aside>
    );
  }

  if (!result) {
    return (
      <aside className="evidence-result evidence-result--idle">
        <div className="evidence-result__metric">
          <span>待处理路径</span>
          <strong>{pathCount}</strong>
        </div>
        <div className="evidence-result__metric">
          <span>默认模式</span>
          <strong>预检</strong>
        </div>
        <div className="evidence-result__metric">
          <span>入库策略</span>
          <strong>增量</strong>
        </div>
      </aside>
    );
  }

  const fileResults = result.file_results || [];
  const errors = result.errors || [];
  const skippedIds = result.skipped_existing_ids || [];
  const ok = result.ok !== false;

  return (
    <aside className={`evidence-result ${ok ? "evidence-result--ok" : "evidence-result--warn"}`}>
      <div className="evidence-result__top">
        <div>
          <h3>{result.dry_run ? "预检结果" : "入库结果"}</h3>
          <p>{result.evidence_db_path || "--"}</p>
        </div>
        <StatusPill label={result.written ? "已写入" : "未写入"} tone={result.written ? "green" : "blue"} />
      </div>

      <div className="evidence-result__grid">
        <Metric label="PDF" value={result.pdf_count} />
        <Metric label="解析记录" value={result.parsed_record_count} />
        <Metric label="新增" value={result.inserted_count} />
        <Metric label="重复" value={result.skipped_existing_count} />
        <Metric label="替换" value={result.replaced_count} />
        <Metric label="总量" value={result.total_after} />
      </div>

      {result.backup_path && (
        <div className="evidence-backup">
          <span>备份</span>
          <strong>{result.backup_path}</strong>
        </div>
      )}

      {fileResults.length > 0 && (
        <div className="evidence-list">
          <div className="evidence-list__title">文件</div>
          {fileResults.map((item, index) => (
            <div className="evidence-list__row" key={`${item.path}-${index}`}>
              <span className={`evidence-dot evidence-dot--${item.status}`} />
              <div>
                <strong>
                  {item.source_type || "--"} · {item.record_count ?? 0} 条
                </strong>
                <p>{item.path}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {skippedIds.length > 0 && (
        <details className="evidence-details">
          <summary>重复 evidence_id</summary>
          <div className="evidence-code-list">
            {skippedIds.slice(0, 20).map((item) => (
              <code key={item}>{item}</code>
            ))}
          </div>
        </details>
      )}

      {errors.length > 0 && (
        <div className="evidence-errors">
          {errors.map((item) => (
            <div key={item.path}>
              <strong>{item.path}</strong>
              <p>{item.error}</p>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}

function Switch({ checked, onChange, label }) {
  return (
    <label className="evidence-switch">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span />
      {label}
    </label>
  );
}

function StatusPill({ label, tone = "slate" }) {
  return <span className={`evidence-pill evidence-pill--${tone}`}>{label}</span>;
}

function Metric({ label, value }) {
  return (
    <div className="evidence-metric">
      <span>{label}</span>
      <strong>{value ?? 0}</strong>
    </div>
  );
}
