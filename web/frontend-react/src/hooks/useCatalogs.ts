import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { CatalogItem, fallbackCatalogs } from "../lib/catalog";

export function useCatalogs() {
  const [talents, setTalents] = useState<CatalogItem[]>(fallbackCatalogs.talents);
  const [spiritRoots, setSpiritRoots] = useState<CatalogItem[]>(fallbackCatalogs.spiritRoots);
  const [families, setFamilies] = useState<CatalogItem[]>(fallbackCatalogs.families);
  const [difficulties, setDifficulties] = useState<CatalogItem[]>(fallbackCatalogs.difficulties);

  useEffect(() => {
    loadCatalog("/api/catalog/talents", fallbackCatalogs.talents, setTalents);
    loadCatalog("/api/catalog/spirit_roots", fallbackCatalogs.spiritRoots, setSpiritRoots);
    loadCatalog("/api/catalog/family_backgrounds", fallbackCatalogs.families, setFamilies);
    loadCatalog("/api/catalog/difficulties", fallbackCatalogs.difficulties, setDifficulties);
  }, []);

  return { talents, spiritRoots, families, difficulties };
}

function loadCatalog<T extends CatalogItem>(
  path: string,
  fallback: T[],
  setter: (items: T[]) => void,
) {
  api<T[]>(path)
    .then((items) => setter(items.length ? items : fallback))
    .catch(() => setter(fallback));
}
