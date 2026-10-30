import { useMemo, useState, type FormEvent } from 'react';
import { ApiError } from '../../api';
import { FormField } from '../../shell/components';
import ConfirmDialog from '../../shell/components/ConfirmDialog';
import { useAuth } from '../auth';
import {
  salesApi,
  type DocumentContent,
  type ReturnCreditNote,
  type ReturnInput,
  type SaleLookup,
  type SaleLookupLine,
} from './api';
import DocumentView from './DocumentView';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

interface LineState {
  quantity: number;
  condition: 'resaleable' | 'damaged';
  selectedSerialIds: number[];
  error?: string;
}

const REASON_PRESETS = ['Changed mind', 'Defective - not sellable', 'Wrong item', 'Other'] as const;

function creditNoteDocument(note: ReturnCreditNote): DocumentContent {
  return (
    note.content ?? {
      kind: 'credit_note',
      credit_note_number: note.credit_note_number,
      created_at: note.created_at,
      store_name: 'ESIMS Electronics',
      location_name: note.location_name,
      processor_name: note.processed_by_username,
      refund_total: note.refund_total,
      reason: note.reason,
      lines: note.lines.map((line) => ({
        id: line.id,
        product_name: line.product_name,
        sku: line.sku,
        quantity: line.quantity,
        refund_amount: line.refund_amount,
        line_total: line.refund_amount,
        serial_numbers: line.serial_numbers,
      })),
    }
  );
}

export default function ReturnsPage() {
  const { user } = useAuth();
  const isManagerOrAdmin = user?.role === 'admin' || user?.role === 'manager';

  const [invoiceInput, setInvoiceInput] = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState('');
  const [sale, setSale] = useState<SaleLookup | null>(null);

  const [lineStates, setLineStates] = useState<Record<number, LineState>>({});
  const [reasonPreset, setReasonPreset] = useState<string>('Changed mind');
  const [reasonNote, setReasonNote] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [creditNote, setCreditNote] = useState<ReturnCreditNote | null>(null);

  // Manager override state
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [approvalUsername, setApprovalUsername] = useState('');
  const [approvalPassword, setApprovalPassword] = useState('');
  const [approvalError, setApprovalError] = useState('');

  async function handleLookup(e: FormEvent) {
    e.preventDefault();
    const query = invoiceInput.trim();
    if (!query) {
      setLookupError('Invoice not found');
      setSale(null);
      setCreditNote(null);
      return;
    }

    setLookupLoading(true);
    setLookupError('');
    setSubmitError('');
    setCreditNote(null);

    try {
      const data = await salesApi.lookupByInvoice(query);
      setSale(data);
      // Initialize line states
      const initial: Record<number, LineState> = {};
      data.lines.forEach((line) => {
        initial[line.id] = {
          quantity: 0,
          condition: 'resaleable',
          selectedSerialIds: [],
        };
      });
      setLineStates(initial);
    } catch (err: unknown) {
      setSale(null);
      if (err instanceof ApiError && err.status === 404) {
        setLookupError('Invoice not found');
      } else if (err instanceof ApiError) {
        setLookupError(err.message || 'Invoice not found');
      } else {
        setLookupError('Invoice not found');
      }
    } finally {
      setLookupLoading(false);
    }
  }

  function handleQuantityChange(line: SaleLookupLine, value: number) {
    const qty = Math.max(0, Math.min(line.quantity_returnable, Math.floor(value) || 0));
    setLineStates((prev) => ({
      ...prev,
      [line.id]: {
        ...prev[line.id],
        quantity: qty,
        error: undefined,
      },
    }));
  }

  function handleConditionChange(lineId: number, condition: 'resaleable' | 'damaged') {
    setLineStates((prev) => ({
      ...prev,
      [lineId]: {
        ...prev[lineId],
        condition,
        error: undefined,
      },
    }));
  }

  function handleSerialToggle(line: SaleLookupLine, serialId: number) {
    setLineStates((prev) => {
      const current = prev[line.id]?.selectedSerialIds || [];
      const next = current.includes(serialId)
        ? current.filter((id) => id !== serialId)
        : [...current, serialId];
      return {
        ...prev,
        [line.id]: {
          ...prev[line.id],
          selectedSerialIds: next,
          quantity: next.length,
          error: undefined,
        },
      };
    });
  }

  function handleReasonChange(newReason: string) {
    setReasonPreset(newReason);
    if (newReason === 'Defective - not sellable') {
      // Set all line conditions to damaged by default
      setLineStates((prev) => {
        const next: Record<number, LineState> = {};
        for (const [idStr, state] of Object.entries(prev)) {
          next[Number(idStr)] = {
            ...state,
            condition: 'damaged',
          };
        }
        return next;
      });
    }
  }

  // Calculate refund estimate
  const { totalUnitsSelected, estimatedRefundTotal } = useMemo(() => {
    if (!sale) return { totalUnitsSelected: 0, estimatedRefundTotal: 0 };
    let units = 0;
    let est = 0;
    for (const line of sale.lines) {
      const state = lineStates[line.id];
      const qty = state?.quantity || 0;
      if (qty > 0) {
        units += qty;
        const lineTotal = Number(line.line_total);
        const sold = line.quantity;
        const already = line.quantity_returned;
        const lineRefund =
          Math.round(((lineTotal * (already + qty)) / sold) * 100) / 100 -
          Math.round(((lineTotal * already) / sold) * 100) / 100;
        est += lineRefund;
      }
    }
    return {
      totalUnitsSelected: units,
      estimatedRefundTotal: Math.round(est * 100) / 100,
    };
  }, [sale, lineStates]);

  function handleProcessClick() {
    if (!sale || totalUnitsSelected === 0 || isSubmitting) return;

    // Check if manager approval is required
    if (sale.requires_manager_approval && !isManagerOrAdmin) {
      setApprovalOpen(true);
      setApprovalError('');
      setApprovalPassword('');
      return;
    }

    executeReturn();
  }

  async function executeReturn(approval?: { username: string; password: string }) {
    if (!sale || totalUnitsSelected === 0 || isSubmitting) return;

    setIsSubmitting(true);
    setSubmitError('');

    const linesPayload = sale.lines
      .filter((line) => (lineStates[line.id]?.quantity || 0) > 0)
      .map((line) => {
        const state = lineStates[line.id];
        const isSerial = line.returnable_serial_ids && line.returnable_serial_ids.length > 0;
        return {
          sale_line_id: line.id,
          quantity: state.quantity,
          condition: state.condition,
          ...(isSerial ? { serial_number_ids: state.selectedSerialIds } : {}),
        };
      });

    const fullReason = reasonNote.trim() ? `${reasonPreset}: ${reasonNote.trim()}` : reasonPreset;

    const payload: ReturnInput = {
      invoice_number: sale.invoice.invoice_number,
      lines: linesPayload,
      reason: fullReason,
      ...(approval ? { manager_approval: approval } : {}),
    };

    try {
      const note = await salesApi.processReturn(payload);
      setCreditNote(note);
      setApprovalOpen(false);
      setApprovalPassword('');
      setSale(null);
    } catch (err: unknown) {
      if (approval) {
        setApprovalError('Manager approval failed.');
        setApprovalPassword('');
      } else if (err instanceof ApiError) {
        if (
          err.status === 403 &&
          (err.fields?.code === 'manager_approval_required' ||
            err.message.includes('Manager approval'))
        ) {
          setApprovalOpen(true);
          setApprovalError('');
          setApprovalPassword('');
          return;
        }

        if (err.status === 422 && err.fields && Object.keys(err.fields).length > 0) {
          const nextErrors: Record<number, string> = {};
          for (const [field, msg] of Object.entries(err.fields)) {
            if (field.startsWith('lines.')) {
              const parts = field.split('.');
              const index = Number(parts[1]);
              const affectedLine = linesPayload[index];
              if (affectedLine) {
                nextErrors[affectedLine.sale_line_id] = msg;
              }
            } else {
              setSubmitError(msg);
            }
          }
          if (Object.keys(nextErrors).length > 0) {
            setLineStates((prev) => {
              const updated = { ...prev };
              for (const [id, msg] of Object.entries(nextErrors)) {
                if (updated[Number(id)]) {
                  updated[Number(id)] = { ...updated[Number(id)], error: msg };
                }
              }
              return updated;
            });
          }
        } else {
          setSubmitError(err.message || 'Failed to process return.');
        }
      } else {
        setSubmitError('Failed to process return.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleApprovalConfirm() {
    if (!approvalUsername.trim() || !approvalPassword.trim() || isSubmitting) return;
    executeReturn({
      username: approvalUsername.trim(),
      password: approvalPassword,
    });
  }

  function handleNewReturn() {
    setCreditNote(null);
    setSale(null);
    setInvoiceInput('');
    setLookupError('');
    setSubmitError('');
    setLineStates({});
  }

  return (
    <div className="returns-page">
      <header className="page-header">
        <h1>Returns</h1>
      </header>

      {/* Result Panel */}
      {creditNote && (
        <section className="result-panel" aria-labelledby="result-title">
          <div className="result-header">
            <h2 id="result-title">Return processed</h2>
            <button type="button" className="primary" onClick={handleNewReturn}>
              New return
            </button>
          </div>
          <div className="result-summary">
            <p>
              <strong>Credit Note:</strong> {creditNote.credit_note_number}
            </p>
            <p>
              <strong>Invoice:</strong>{' '}
              {creditNote.content?.invoice_label ??
                `INV-${String(creditNote.invoice_number).padStart(4, '0')}`}
            </p>
            <p>
              <strong>Location:</strong> {creditNote.location_name}
            </p>
            <p>
              <strong>Refund Total:</strong> {money.format(Number(creditNote.refund_total))}
            </p>
            <p>
              <strong>Processed by:</strong> {creditNote.processed_by_username}
            </p>
            {creditNote.approved_by_username && (
              <p>
                <strong>Approved by:</strong> {creditNote.approved_by_username}
              </p>
            )}
            <p>
              <strong>Reason:</strong> {creditNote.reason}
            </p>
          </div>

          <DocumentView
            document={creditNoteDocument(creditNote)}
            pdfUrl={`/sales/returns/${creditNote.return_id}/pdf`}
          />

          <table className="data-table" aria-label="Returned items">
            <thead>
              <tr>
                <th>Item</th>
                <th>SKU</th>
                <th>Qty</th>
                <th>Condition</th>
                <th>Status</th>
                <th>Refund</th>
              </tr>
            </thead>
            <tbody>
              {creditNote.lines.map((rl) => (
                <tr key={rl.id}>
                  <td>
                    <div>{rl.product_name}</div>
                    {rl.variant_sku && <div className="text-muted">{rl.variant_sku}</div>}
                    {rl.serial_numbers.length > 0 && (
                      <div className="text-muted">Serials: {rl.serial_numbers.join(', ')}</div>
                    )}
                  </td>
                  <td>{rl.sku}</td>
                  <td>{rl.quantity}</td>
                  <td>{rl.condition}</td>
                  <td>{rl.restocked ? 'Restocked' : 'Not added to sellable stock (damaged)'}</td>
                  <td>{money.format(Number(rl.refund_amount))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Lookup Form */}
      {!creditNote && (
        <section className="lookup-section">
          <form onSubmit={handleLookup} className="lookup-form">
            <FormField label="Invoice number" error={lookupError}>
              {(control) => (
                <div className="lookup-input-group">
                  <input
                    {...control}
                    type="text"
                    placeholder="e.g. 5002 or INV-5002"
                    value={invoiceInput}
                    onChange={(e) => {
                      setInvoiceInput(e.target.value);
                      if (lookupError) setLookupError('');
                    }}
                    autoFocus
                  />
                  <button type="submit" disabled={lookupLoading}>
                    {lookupLoading ? 'Looking up...' : 'Look up'}
                  </button>
                </div>
              )}
            </FormField>
          </form>
        </section>
      )}

      {/* Sale Details & Return Form */}
      {!creditNote && sale && (
        <section className="sale-return-section">
          <div className="sale-summary-card">
            <div className="summary-row">
              <div>
                <strong>Invoice:</strong> {sale.invoice.invoice_label}
              </div>
              <div>
                <strong>Date:</strong> {new Date(sale.sold_at).toLocaleDateString()}
              </div>
              <div>
                <strong>Location:</strong> {sale.location_name}
              </div>
              <div>
                <strong>Days since sale:</strong> {sale.days_since_sale}
              </div>
              {sale.return_status === 'partially_returned' && (
                <span className="badge warning">Partially Returned</span>
              )}
              {sale.return_status === 'fully_returned' && (
                <span className="badge danger">Fully Returned</span>
              )}
            </div>

            {sale.requires_manager_approval && !isManagerOrAdmin && (
              <div className="warning-banner" role="alert">
                Older than 30 days: Manager approval required
              </div>
            )}
          </div>

          {submitError && (
            <div className="error-banner" role="alert">
              {submitError}
            </div>
          )}

          <div className="table-container">
            <table className="data-table" aria-label="Sale lines to return">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Sold</th>
                  <th>Already returned</th>
                  <th>Returnable</th>
                  <th>Return quantity</th>
                  <th>Condition</th>
                </tr>
              </thead>
              <tbody>
                {sale.lines.map((line) => {
                  const state = lineStates[line.id] || {
                    quantity: 0,
                    condition: 'resaleable',
                    selectedSerialIds: [],
                  };
                  const isReturnable = line.quantity_returnable > 0;
                  const isSerial =
                    line.returnable_serial_ids && line.returnable_serial_ids.length > 0;

                  return (
                    <tr key={line.id} className={!isReturnable ? 'row-disabled' : undefined}>
                      <td>
                        <strong>{line.product_name}</strong>
                        <div className="text-muted">SKU: {line.sku}</div>
                        {line.variant_sku && (
                          <div className="text-muted">Variant: {line.variant_sku}</div>
                        )}
                        {line.variant_attributes && (
                          <div className="text-muted">
                            {Object.entries(line.variant_attributes)
                              .map(([k, v]) => `${k}: ${v}`)
                              .join(', ')}
                          </div>
                        )}
                        {state.error && <div className="field-error">{state.error}</div>}
                      </td>
                      <td>{line.quantity}</td>
                      <td>{line.quantity_returned}</td>
                      <td>{line.quantity_returnable}</td>
                      <td>
                        {isSerial ? (
                          <div className="serials-selection">
                            <div className="serial-count">
                              Selected: {state.selectedSerialIds.length}
                            </div>
                            <div className="serial-checkbox-list">
                              {line.returnable_serials.map((sn, idx) => {
                                const snId = line.returnable_serial_ids[idx];
                                const checked = state.selectedSerialIds.includes(snId);
                                return (
                                  <label key={snId} className="serial-label">
                                    <input
                                      type="checkbox"
                                      disabled={!isReturnable || isSubmitting}
                                      checked={checked}
                                      onChange={() => handleSerialToggle(line, snId)}
                                    />
                                    <span>{sn}</span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          <input
                            type="number"
                            min="0"
                            max={line.quantity_returnable}
                            disabled={!isReturnable || isSubmitting}
                            value={state.quantity || ''}
                            placeholder="0"
                            onChange={(e) => handleQuantityChange(line, Number(e.target.value))}
                            className="qty-input"
                            aria-label={`Return quantity for ${line.product_name}`}
                          />
                        )}
                      </td>
                      <td>
                        <select
                          disabled={!isReturnable || isSubmitting}
                          value={state.condition}
                          onChange={(e) =>
                            handleConditionChange(
                              line.id,
                              e.target.value as 'resaleable' | 'damaged',
                            )
                          }
                          aria-label={`Condition for ${line.product_name}`}
                        >
                          <option value="resaleable">Resaleable</option>
                          <option value="damaged">Damaged</option>
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="return-options">
            <FormField label="Reason for return">
              {(control) => (
                <select
                  {...control}
                  value={reasonPreset}
                  disabled={isSubmitting}
                  onChange={(e) => handleReasonChange(e.target.value)}
                >
                  {REASON_PRESETS.map((preset) => (
                    <option key={preset} value={preset}>
                      {preset}
                    </option>
                  ))}
                </select>
              )}
            </FormField>

            <FormField label="Additional notes (optional)">
              {(control) => (
                <input
                  {...control}
                  type="text"
                  maxLength={400}
                  placeholder="Notes about the return"
                  value={reasonNote}
                  disabled={isSubmitting}
                  onChange={(e) => setReasonNote(e.target.value)}
                />
              )}
            </FormField>
          </div>

          <div className="return-footer">
            <div className="refund-estimate-box">
              <span className="estimate-label">Refund estimate:</span>{' '}
              <strong className="estimate-value">{money.format(estimatedRefundTotal)}</strong>{' '}
              <span className="text-muted">(Estimated amount; server calculates exact refund)</span>
            </div>

            <button
              type="button"
              className="primary"
              disabled={totalUnitsSelected === 0 || isSubmitting}
              onClick={handleProcessClick}
            >
              {isSubmitting ? 'Processing return...' : 'Process return'}
            </button>
          </div>
        </section>
      )}

      {/* Manager Approval Dialog */}
      <ConfirmDialog
        open={approvalOpen}
        title="Manager approval required"
        confirmLabel={isSubmitting ? 'Approving...' : 'Approve'}
        cancelLabel="Cancel"
        confirmDisabled={!approvalUsername.trim() || !approvalPassword.trim() || isSubmitting}
        confirmVariant="primary"
        onConfirm={handleApprovalConfirm}
        onCancel={() => {
          setApprovalOpen(false);
          setApprovalPassword('');
          setApprovalError('');
        }}
      >
        <p>This return is older than 30 days and requires a Manager override.</p>
        {approvalError && (
          <div className="error-banner" role="alert">
            {approvalError}
          </div>
        )}
        <FormField label="Manager username">
          {(control) => (
            <input
              {...control}
              type="text"
              value={approvalUsername}
              disabled={isSubmitting}
              onChange={(e) => setApprovalUsername(e.target.value)}
              autoFocus
            />
          )}
        </FormField>
        <FormField label="Manager password">
          {(control) => (
            <input
              {...control}
              type="password"
              autoComplete="off"
              value={approvalPassword}
              disabled={isSubmitting}
              onChange={(e) => setApprovalPassword(e.target.value)}
            />
          )}
        </FormField>
      </ConfirmDialog>
    </div>
  );
}
