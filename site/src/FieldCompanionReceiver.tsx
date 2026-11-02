import {useMemo, useState} from 'react'
import {createFieldCompanionReceiver, parseFieldCompanion, FIELD_MAX_BYTES, FIELD_ROUTES, type FieldCompanion} from './field-companion.mjs'
import './field-companion.css'

const routeNames = {live: 'PhiOS Live', xr: 'PhiOS XR', mobile: 'PhiOS Mobile'} as const

function browserStorage(): Storage | null {
  try {return window.localStorage} catch {return null}
}

export default function FieldCompanionReceiver() {
  const receiver = useMemo(() => createFieldCompanionReceiver({storage: browserStorage()}), [])
  const [record, setRecord] = useState<FieldCompanion | null>(() => receiver.snapshot())
  const [notice, setNotice] = useState('')

  const handleImport = async (file?: File) => {
    if (!file) return
    if (file.size > FIELD_MAX_BYTES) {
      setNotice('Rejected: Field Companion JSON exceeds 16 KiB.')
      return
    }
    try {
      const text = await file.text()
      // Validate without changing any state or permissions, then require approval.
      parseFieldCompanion(text)
      if (!window.confirm('Import Field Companion callsign, pins and last portal into this browser only? It will not change host settings, achievements, or permissions.')) {
        setNotice('Import canceled. No changes made.')
        return
      }
      const outcome = receiver.importJSON(text)
      setRecord(outcome.record)
      setNotice(outcome.persisted ? 'Companion preferences saved in this browser.' :
        'Browser storage blocked. Preferences are available for this session only.')
    } catch {
      setNotice('Rejected: invalid or unsupported Field Companion v1 JSON.')
    }
  }
  const handleExport = () => {
    const data = receiver.exportJSON()
    if (!data) return
    const url = URL.createObjectURL(new Blob([data], {type:'application/json'}))
    const link = document.createElement('a')
    link.href = url
    link.download = 'phi-field-companion-v1.json'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1500)
    setNotice('Plaintext JSON exported. Keep a copy somewhere you control.')
  }
  const handleRemove = () => {
    if (!record || !window.confirm('Remove only this app’s imported Field Companion preferences?')) return
    receiver.clear()
    setRecord(null)
    setNotice('Imported Companion preferences removed. Host settings are unchanged.')
  }
  return (
    <section className="field-receiver" aria-labelledby="field-receiver-title">
      <div className="field-receiver__heading">
        <div>
          <span className="field-receiver__kicker">RUNG 5 / MANUAL CONTINUITY</span>
          <h2 id="field-receiver-title">Φ Field Companion</h2>
        </div>
        <a href="https://michaelwave369.github.io/phi-field/">BACK TO THE FIELD ↗</a>
      </div>
      <p>Bring your optional callsign and three portal shortcuts from Φ Field. Import a JSON file you chose, or remove it whenever you want. This is not an account or a permission grant.</p>
      <div className="field-receiver__summary" aria-live="polite">
        <strong>{record ? (record.profile.alias || 'Field Explorer') : 'NO COMPANION IMPORTED'}</strong>
        <span>{record ? 'DISPLAY CALLSIGN ONLY · NOT VERIFIED IDENTITY' : 'ALL FEATURES STAY AVAILABLE'}</span>
      </div>
      {record && <div className="field-receiver__route">
        <strong>PINNED PORTALS</strong>
        <div>{record.profile.pinned.length ? record.profile.pinned.map(id => (
          <a key={id} href={FIELD_ROUTES[id]}>{routeNames[id]} ↗</a>
        )) : <span>No shortcuts pinned.</span>}</div>
        {record.profile.last && <a href={FIELD_ROUTES[record.profile.last]}>CONTINUE: {routeNames[record.profile.last]} ↗</a>}
      </div>}
      <div className="field-receiver__actions">
        <label htmlFor="field-companion-import">IMPORT COMPANION JSON (16 KiB MAX)</label>
        <input id="field-companion-import" type="file" accept=".json,application/json"
          onChange={e => {const file = e.currentTarget.files?.[0]; e.currentTarget.value = ''; void handleImport(file)}}/>
        <button type="button" disabled={!record} onClick={handleExport}>EXPORT COPY</button>
        <button type="button" disabled={!record} onClick={handleRemove}>REMOVE IMPORT</button>
      </div>
      <p className="field-receiver__notice" role="status">{notice || (record ?
        (receiver.persisted() ? 'Stored on this browser origin only.' : 'Session-only; export to keep a copy.') :
        'Nothing is automatically read from Φ Field or other websites.')}</p>
      <p className="field-receiver__fine">Appearance is carried for future manual portability but does not change this host. PhiOperator Passport, saved work, XR controls, and PhiOS authority are untouched. No background sync.</p>
    </section>
  )
}
