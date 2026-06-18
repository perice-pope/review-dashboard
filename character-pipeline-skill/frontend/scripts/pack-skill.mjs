// Packs the Character Pipeline *skill* into public/character-pipeline-skill.zip
// so the landing page can offer it as a download. Runs as `prebuild`, so Vercel
// regenerates a fresh zip on every deploy.
//
// Ships ONLY the skill (SKILL.md, README, scripts, references, .env.example).
// Never the website (frontend/), never secrets (.env), never generated assets.
import { createWriteStream } from 'node:fs'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import archiver from 'archiver'

const here = dirname(fileURLToPath(import.meta.url))
const skillRoot = resolve(here, '..', '..')          // character-pipeline-skill/
const outDir = resolve(here, '..', 'public')         // frontend/public/
const outFile = resolve(outDir, 'character-pipeline-skill.zip')

// Curated allowlist — extracts as a clean `character-pipeline/` folder.
const FILES = ['SKILL.md', 'README.md', '.env.example']
const DIRS = ['scripts', 'references']
const IGNORE = ['**/__pycache__/**', '**/*.pyc', '**/.env', '**/*.zip', '**/.DS_Store']

await mkdir(outDir, { recursive: true })

const output = createWriteStream(outFile)
const archive = archiver('zip', { zlib: { level: 9 } })

const done = new Promise((res, rej) => {
  output.on('close', res)
  archive.on('warning', (e) => (e.code === 'ENOENT' ? console.warn(e.message) : rej(e)))
  archive.on('error', rej)
})

archive.pipe(output)
for (const f of FILES) archive.file(resolve(skillRoot, f), { name: `character-pipeline/${f}` })
for (const d of DIRS) archive.directory(resolve(skillRoot, d), `character-pipeline/${d}`, (entry) =>
  IGNORE.some((g) => entry.name.includes('__pycache__') || entry.name.endsWith('.pyc')) ? false : entry,
)
await archive.finalize()
await done

console.log(`pack-skill: wrote ${outFile} (${archive.pointer()} bytes)`)
