"use client";

import { useEffect, useRef } from "react";
import { useLocale } from "@/lib/i18n/context";
import ar from "@/lib/i18n/messages/literals.ar.json";
import fr from "@/lib/i18n/messages/literals.fr.json";
import keyedAr from "@/lib/i18n/messages/ar.json";
import keyedEn from "@/lib/i18n/messages/en.json";
import keyedFr from "@/lib/i18n/messages/fr.json";

function flattenValues(value: unknown, result: string[] = []): string[] {
  if (typeof value === "string") result.push(value);
  else if (value && typeof value === "object") Object.values(value).forEach((child) => flattenValues(child, result));
  return result;
}

function keyedLiteralMap(target: unknown): Record<string, string> {
  const sources = flattenValues(keyedEn);
  const targets = flattenValues(target);
  return Object.fromEntries(sources.map((source, index) => [source, targets[index] ?? source]));
}

const LITERALS = {
  ar: { ...keyedLiteralMap(keyedAr), ...ar },
  fr: { ...keyedLiteralMap(keyedFr), ...fr }
};
const TRANSLATED_ATTRIBUTES = ["aria-label", "placeholder", "title"] as const;

/**
 * Localizes legacy and redesigned screens whose visible copy predates the keyed
 * translation catalogue. Keeping this at the application boundary also covers
 * status messages and dialog content inserted after the initial render.
 */
export function LocalizedContent({ children }: { children: React.ReactNode }) {
  const { locale } = useLocale();
  const rootRef = useRef<HTMLDivElement>(null);
  const sourceText = useRef(new WeakMap<Text, string>());
  const sourceAttributes = useRef(new WeakMap<Element, Map<string, string>>());

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const dictionary = locale === "en" ? null : LITERALS[locale];

    function translated(value: string): string {
      if (!dictionary) return value;
      const leading = value.match(/^\s*/)?.[0] ?? "";
      const trailing = value.match(/\s*$/)?.[0] ?? "";
      const key = value.trim();
      if (!key) return value;
      const exact = dictionary[key as keyof typeof dictionary];
      if (exact) return `${leading}${exact}${trailing}`;

      // Quantities, dates, and identifiers are often rendered beside a static
      // label in one text node. Translate the known label while preserving the
      // live value supplied by the application.
      if (/\d/.test(key)) {
        const candidates = Object.keys(dictionary).filter(
          (source) => source.length > 2 && (key.startsWith(`${source} `) || key.endsWith(` ${source}`))
        );
        const source = candidates.sort((a, b) => b.length - a.length)[0];
        if (source) return `${leading}${key.replace(source, dictionary[source as keyof typeof dictionary])}${trailing}`;
      }
      return value;
    }

    function localizeNode(node: Node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node as Text;
        const parent = text.parentElement;
        if (!parent || parent.closest("script, style, code, pre")) return;
        if (!sourceText.current.has(text)) sourceText.current.set(text, text.data);
        text.data = translated(sourceText.current.get(text) ?? text.data);
        return;
      }

      if (!(node instanceof Element)) return;
      let originals = sourceAttributes.current.get(node);
      if (!originals) {
        originals = new Map();
        sourceAttributes.current.set(node, originals);
      }
      for (const attribute of TRANSLATED_ATTRIBUTES) {
        if (!node.hasAttribute(attribute)) continue;
        if (!originals.has(attribute)) originals.set(attribute, node.getAttribute(attribute) ?? "");
        node.setAttribute(attribute, translated(originals.get(attribute) ?? ""));
      }

      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
      let child = walker.nextNode();
      while (child) {
        localizeNode(child);
        child = walker.nextNode();
      }
    }

    localizeNode(root);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) localizeNode(node);
      }
    });
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [locale]);

  return <div ref={rootRef} style={{ display: "contents" }}>{children}</div>;
}
