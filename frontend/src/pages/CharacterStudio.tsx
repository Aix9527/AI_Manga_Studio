import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import * as api from "@/api/character";
import { userMessage } from "@/api/client";
import ReferenceGallery, { type ReferenceImage } from "@/components/ReferenceGallery";
import { selectedCharacterSelector, useCharacterStore } from "@/state/characterStore";
import { useWorkspaceStore } from "@/state/workspaceStore";

const VALUE_LABELS: Record<string, string> = {
  protagonist: "主角",
  antagonist: "反派",
  supporting: "配角",
  male: "男",
  female: "女",
  unknown: "未知",
  human: "人类",
  friend: "朋友",
  ally: "盟友",
  enemy: "敌对",
  family: "家人",
  mentor: "导师",
};

const FIELD_LABELS: Record<string, string> = {
  hair_color: "发色",
  eye_color: "瞳色",
  height: "身高",
  clothing: "服装",
  feature: "辨识特征",
  brave: "勇气",
  temperament: "气质",
  motivation: "动机",
  flaw: "弱点",
};

function translate(value: unknown): string {
  if (typeof value === "string") return VALUE_LABELS[value.toLowerCase()] ?? value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(translate).join("、");
  return value == null ? "暂无" : "已记录补充信息";
}

function enumLabel(value: unknown, fallback: string): string {
  if (typeof value !== "string" || !value.trim()) return fallback;
  return VALUE_LABELS[value.toLowerCase()] ?? fallback;
}

function SettingList({ values }: { values?: Record<string, unknown> }) {
  const unknownLabels = new Map<string, string>();
  let unknownIndex = 0;
  for (const key of Object.keys(values ?? {})) {
    if (!FIELD_LABELS[key]) unknownLabels.set(key, `补充设定 ${++unknownIndex}`);
  }
  if (!values || Object.keys(values).length === 0) return <p className="workspace-empty-copy">暂无设定</p>;
  return (
    <dl className="character-settings">
      {Object.entries(values).map(([key, value]) => (
        <div key={key}>
          <dt>{FIELD_LABELS[key] ?? unknownLabels.get(key)}</dt>
          <dd>{translate(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

const CharacterDetail: React.FC<{ character: api.CharacterData }> = ({ character }) => {
  const relationshipMap = useCharacterStore((state) => state.relationships);
  const relationships = character.id ? relationshipMap[character.id] ?? [] : [];
  const relationshipError = useCharacterStore((state) => state.relationshipError);
  const loadRelationships = useCharacterStore((state) => state.loadRelationships);
  const [references, setReferences] = useState<ReferenceImage[]>([]);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const [selectedReference, setSelectedReference] = useState<string>();
  const [imageUrl, setImageUrl] = useState("");
  const [checking, setChecking] = useState(false);
  const [consistencyError, setConsistencyError] = useState<string | null>(null);
  const [result, setResult] = useState<api.ConsistencyResult | null>(null);
  const imageRequest = useRef(0);
  const consistencyRequest = useRef(0);

  const loadReferences = async () => {
    if (!character.id) return;
    const token = ++imageRequest.current;
    setReferenceError(null);
    setReferences([]);
    try {
      const images = await api.listCharacterImages(character.id);
      if (token !== imageRequest.current) return;
      setReferences(images.map((image, index) => ({
        id: image.id ?? `${character.id}-reference-${index + 1}`,
        url: image.url,
        label: image.label ?? "reference",
        characterId: character.id!,
      })));
    } catch (error) {
      if (token !== imageRequest.current) return;
      setReferenceError(userMessage(error));
    }
  };

  useEffect(() => {
    imageRequest.current += 1;
    consistencyRequest.current += 1;
    setImageUrl("");
    setChecking(false);
    setResult(null);
    setConsistencyError(null);
    if (character.id) {
      void loadRelationships(character.id);
      void loadReferences();
    }
    return () => {
      imageRequest.current += 1;
      consistencyRequest.current += 1;
    };
  }, [character.id]);

  const checkConsistency = async () => {
    if (!character.id || !imageUrl.trim()) return;
    const requestToken = ++consistencyRequest.current;
    setChecking(true);
    setConsistencyError(null);
    setResult(null);
    try {
      const nextResult = await api.checkCharacterConsistency(character.id, imageUrl.trim());
      if (requestToken !== consistencyRequest.current) return;
      setResult(nextResult);
    } catch (error) {
      if (requestToken !== consistencyRequest.current) return;
      setConsistencyError(userMessage(error));
    } finally {
      if (requestToken === consistencyRequest.current) setChecking(false);
    }
  };

  return (
    <div className="character-detail">
      <header>
        <h2>{character.name}</h2>
        <p>
          {[
            enumLabel(character.role, "其他角色"),
            enumLabel(character.gender, "未说明性别"),
            enumLabel(character.species, "其他物种"),
          ].join(" · ")}
          {character.age ? ` · ${character.age} 岁` : ""}
        </p>
      </header>

      <section><h3>外观设定</h3><SettingList values={character.appearance} /></section>
      <section><h3>性格设定</h3><SettingList values={character.personality} /></section>
      <section>
        <h3>人物关系</h3>
        {relationshipError ? (
          <div className="workspace-inline-error" role="alert">
            <p>{relationshipError}</p>
            <button type="button" onClick={() => character.id && void loadRelationships(character.id)}>重试关系加载</button>
          </div>
        ) : relationships.length ? (
          <ul className="character-relationships">
            {relationships.map((relationship, index) => (
              <li key={relationship.id ?? `${relationship.target_id}-${index}`}>
                <strong>{enumLabel(relationship.relation_type, "其他关系")}</strong>
                <span>
                  {relationship.related_name || `关联角色 ${relationship.target_id}`}
                  {relationship.description ? ` · ${relationship.description}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : <p className="workspace-empty-copy">暂无人物关系</p>}
      </section>
      <section>
        <h3>一致性检查</h3>
        <div className="workspace-form-row">
          <label htmlFor={`consistency-${character.id}`}>待检查图像地址</label>
          <input id={`consistency-${character.id}`} value={imageUrl} onChange={(event) => setImageUrl(event.target.value)} />
          <button type="button" disabled={checking || !imageUrl.trim()} onClick={() => void checkConsistency()}>
            {checking ? "正在检查" : "检查一致性"}
          </button>
        </div>
        {consistencyError ? <p className="workspace-error" role="alert">{consistencyError}</p> : null}
        {result ? (
          <dl className="consistency-result">
            <div><dt>结果</dt><dd>{result.passed ? "通过" : "未通过"}</dd></div>
            <div><dt>相似度</dt><dd>{result.similarity.toFixed(3)}</dd></div>
            <div><dt>阈值</dt><dd>{result.threshold.toFixed(3)}</dd></div>
          </dl>
        ) : null}
      </section>
      <section>
        <h3>角色参考图</h3>
        {referenceError ? (
          <div className="workspace-inline-error" role="alert">
            <p>{referenceError}</p>
            <button type="button" onClick={() => void loadReferences()}>重试参考图加载</button>
          </div>
        ) : (
          <ReferenceGallery
            characterId={character.id ?? ""}
            characterName={character.name}
            references={references}
            selectedId={selectedReference}
            onSelect={setSelectedReference ? (reference) => setSelectedReference(reference.id) : undefined}
          />
        )}
      </section>
    </div>
  );
};

export const CharacterBiblePanel: React.FC = () => {
  const store = useCharacterStore();
  const selected = selectedCharacterSelector(store);
  const selectObject = useWorkspaceStore((state) => state.selectObject);
  const [query, setQuery] = useState("");
  const filtered = useMemo(
    () => store.characters.filter((item) => item.name.toLowerCase().includes(query.trim().toLowerCase())),
    [query, store.characters],
  );

  if (!store.loading && !store.error && store.characters.length === 0) {
    return (
      <div className="workspace-empty-state">
        <h2>尚未提取角色</h2>
        <p>导入小说后可建立角色圣经与一致性参考。</p>
        <Link to="/overview#import">导入并解析小说</Link>
      </div>
    );
  }

  return (
    <div className="character-workspace">
      <aside className="character-list" aria-label="角色列表">
        <label htmlFor="character-search">搜索角色</label>
        <input id="character-search" placeholder="搜索角色" value={query} onChange={(event) => setQuery(event.target.value)} />
        {store.loading ? <p className="workspace-muted" role="status">正在加载角色</p> : null}
        {store.error ? (
          <div className="workspace-inline-error" role="alert">
            <p>{store.error}</p>
          </div>
        ) : null}
        <div className="character-list__items">
          {filtered.map((item) => {
            const pressed = selected?.id === item.id;
            return (
              <button
                type="button"
                key={item.id ?? item.name}
                aria-pressed={pressed}
                onClick={() => {
                  if (!item.id) return;
                  store.selectCharacter(item.id);
                  selectObject({ type: "角色", id: item.id });
                }}
              >
                <strong>{item.name}</strong>
                <span>{[
                  enumLabel(item.role, "其他角色"),
                  enumLabel(item.gender, "未说明性别"),
                ].join(" · ")}</span>
              </button>
            );
          })}
        </div>
      </aside>
      <div className="character-detail-pane">
        {selected ? <CharacterDetail character={selected} /> : <p className="workspace-empty-copy">选择角色查看详细设定</p>}
      </div>
    </div>
  );
};

export default CharacterBiblePanel;
