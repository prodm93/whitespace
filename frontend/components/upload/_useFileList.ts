import { useCallback, useState } from "react";
import type { UploadedFile } from "@/types";
import { nextId } from "./DropZone";

function toUploadedFile(file: File): UploadedFile {
  return { id: nextId(), file, name: file.name, size: file.size };
}

export function useFileList() {
  const [files, setFiles] = useState<UploadedFile[]>([]);

  const add = useCallback((incoming: File[]) => {
    setFiles((prev) => [...prev, ...incoming.map(toUploadedFile)]);
  }, []);

  const remove = useCallback((id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  return { files, add, remove } as const;
}
