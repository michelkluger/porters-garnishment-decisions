import { FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { submitLetter } from "./api";
import { DecisionCard, type Item } from "./DecisionCard";
import "./index.css";

const isText = (f: File) => f.type === "text/plain" || f.name.toLowerCase().endsWith(".txt");

// Cap in-flight model calls across all drops so a big batch doesn't trip provider rate limits.
const MAX_UPLOADS = 3;
let active = 0;
const waiting: (() => void)[] = [];

async function limited<T>(task: () => Promise<T>): Promise<T> {
  if (active < MAX_UPLOADS) active++;
  else await new Promise<void>((resolve) => waiting.push(resolve)); // a finishing task hands us its slot
  try {
    return await task();
  } finally {
    const next = waiting.shift();
    if (next) next();
    else active--;
  }
}

export function App() {
  const [items, setItems] = useState<Item[]>([]);

  const settle = (key: string, next: Item) => setItems((xs) => xs.map((x) => (x.key === key ? next : x)));

  async function process(file: File) {
    const key = crypto.randomUUID();
    const base = { key, fileName: file.name };
    setItems((xs) => [{ ...base, state: "pending" }, ...xs]);
    try {
      if (!isText(file)) throw new Error("Only plain-text (.txt) letters for now. PDFs and scans need OCR, which is out of scope.");
      settle(key, { ...base, state: "done", decision: await limited(async () => submitLetter(await file.text())) });
    } catch (e) {
      settle(key, { ...base, state: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  const handleFiles = (files: File[]) => files.forEach(process);

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#E6ECF4_0%,#F0F4F9_420px)]">
      <div className="px-4 pt-4">
        <header className="mx-auto flex max-w-5xl items-center justify-between gap-4 rounded-[50px] border border-[#C5CBD3] bg-[#F8FAFB]/70 px-6 py-3 backdrop-blur-sm">
          {/* TODO(brand): swap this text wordmark for the Porters logo once usage is agreed */}
          <span className="text-xl font-semibold tracking-tight">Porters</span>
          <span className="text-muted-foreground text-sm">Garnishment decision workbench</span>
        </header>
      </div>

      <main className="mx-auto max-w-5xl space-y-8 px-4 py-12">
        <section className="space-y-3 text-center">
          <h1 className="text-4xl leading-[120%] font-medium tracking-tight md:text-5xl">
            Drop a court letter, see the decision
          </h1>
          <p className="text-muted-foreground mx-auto max-w-2xl text-lg">
            The model reads each letter, explicit rules decide the route, and the decision is stored with the
            evidence behind it.
          </p>
        </section>

        <DropZone onFiles={handleFiles} />

        {items.length > 0 && (
          <section className="space-y-4" aria-label="Decisions">
            {items.map((item) => (
              <DecisionCard key={item.key} item={item} />
            ))}
          </section>
        )}
      </main>
    </div>
  );
}

function DropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false); // ignore moves onto children
      }}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFiles(Array.from(e.dataTransfer.files));
      }}
      className={cn(
        "flex flex-col items-center gap-4 rounded-4xl border-2 border-dashed bg-[linear-gradient(0deg,#F0F4F9_18.6%,#C4D4E9_100%)] px-6 py-12 text-center transition",
        over ? "border-primary ring-primary/15 ring-8" : "border-[#B9BECA]",
      )}
    >
      <FileUp className="text-primary size-10" aria-hidden />
      <div className="space-y-1">
        <p className="text-xl font-medium">Drop letters here</p>
        <p className="text-muted-foreground text-sm">
          One or more plain-text (.txt) court letters. Labelled examples are in <code>samples/</code>.
        </p>
      </div>
      <Button className="rounded-full px-6" onClick={() => input.current?.click()}>
        Choose files
      </Button>
      <input
        ref={input}
        type="file"
        accept=".txt,text/plain"
        multiple
        hidden
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []));
          e.target.value = ""; // allow re-uploading the same file
        }}
      />
    </div>
  );
}
