import { useState } from 'react';
import type { DocumentContent } from './api';

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' });

export default function DocumentView({
  document,
  pdfUrl,
  returnStatus = 'none',
}: {
  document: DocumentContent;
  pdfUrl: string;
  returnStatus?: 'none' | 'partially_returned' | 'fully_returned';
}) {
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [showDocument, setShowDocument] = useState(true);
  const number = document.kind === 'invoice' ? document.invoice_label : document.credit_note_number;

  async function download() {
    setDownloading(true);
    setDownloadError('');
    try {
      const response = await fetch(`/api${pdfUrl}`, { credentials: 'same-origin' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail =
          typeof body.detail === 'string' ? body.detail : 'Could not download the PDF.';
        throw new Error(detail);
      }
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const link = window.document.createElement('a');
      link.href = href;
      link.download =
        response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] ??
        'document.pdf';
      link.click();
      URL.revokeObjectURL(href);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : 'Could not download the PDF.');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="document-view">
      <div className="document-actions">
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
        <button type="button" onClick={download} disabled={downloading}>
          {downloading ? 'Preparing PDF…' : 'Download PDF'}
        </button>
      </div>
      {downloadError && (
        <div role="alert" className="document-download-error">
          <p>{downloadError}</p>
          <button type="button" onClick={download}>
            Retry
          </button>
          <button
            type="button"
            onClick={() => {
              setShowDocument(true);
              setDownloadError('');
            }}
          >
            View on screen
          </button>
        </div>
      )}
      {showDocument && (
        <article className="document-sheet">
          <header className="document-header">
            <div>
              <h1>{document.store_name}</h1>
              <p>{document.location_name}</p>
              {document.location_address && <p>{document.location_address}</p>}
              {document.store_gstin && <p>GSTIN: {document.store_gstin}</p>}
            </div>
            <div className="document-number">
              <h2>{document.kind === 'invoice' ? 'Invoice' : 'Credit note'}</h2>
              <strong>{number}</strong>
              <p>{new Date(document.issued_at ?? document.created_at ?? '').toLocaleString()}</p>
            </div>
          </header>
          <div className="document-meta">
            {(document.cashier_name || document.processor_name) && (
              <span>Cashier: {document.cashier_name ?? document.processor_name}</span>
            )}
            {document.customer_name && <span>Customer: {document.customer_name}</span>}
            {returnStatus !== 'none' && (
              <strong className="badge warning">
                {returnStatus === 'partially_returned' ? 'Partially Returned' : 'Fully Returned'}
              </strong>
            )}
          </div>
          <table className="data-table document-lines">
            <thead>
              <tr>
                <th>Item</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>{document.kind === 'invoice' ? 'Tax' : 'Refund'}</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {document.lines.map((line, index) => (
                <tr key={line.id ?? `${line.sku}-${index}`}>
                  <td>
                    <strong>{line.product_name}</strong>
                    <br />
                    {line.sku}
                    {line.variant_label ? ` · ${line.variant_label}` : ''}
                    {line.serial_numbers?.length ? (
                      <div>Serials: {line.serial_numbers.join(', ')}</div>
                    ) : null}
                  </td>
                  <td>{line.quantity}</td>
                  <td>{money.format(Number(line.unit_price ?? 0))}</td>
                  <td>
                    {money.format(
                      Number(
                        document.kind === 'invoice' ? (line.tax ?? 0) : (line.refund_amount ?? 0),
                      ),
                    )}
                  </td>
                  <td>{money.format(Number(line.line_total ?? line.refund_amount ?? 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {document.kind === 'invoice' ? (
            <>
              <dl className="document-totals">
                <div>
                  <dt>Subtotal</dt>
                  <dd>{money.format(Number(document.subtotal ?? 0))}</dd>
                </div>
                <div>
                  <dt>Discount</dt>
                  <dd>{money.format(Number(document.discount_total ?? 0))}</dd>
                </div>
                <div>
                  <dt>GST ({document.gst_rate}%)</dt>
                  <dd>{money.format(Number(document.tax_total ?? 0))}</dd>
                </div>
                <div className="document-grand-total">
                  <dt>Total</dt>
                  <dd>{money.format(Number(document.total ?? 0))}</dd>
                </div>
              </dl>
              <h3>Payments</h3>
              <ul>
                {(document.payments ?? []).map((payment, index) => (
                  <li key={`${payment.method}-${index}`}>
                    {payment.method}: {money.format(Number(payment.amount))}
                    {payment.reference ? ` · ${payment.reference}` : ''}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <dl className="document-totals">
              <div className="document-grand-total">
                <dt>Refund total</dt>
                <dd>{money.format(Number(document.refund_total ?? 0))}</dd>
              </div>
            </dl>
          )}
          {document.reason && <p>Reason: {document.reason}</p>}
          <footer className="document-footer">Thank you for your business.</footer>
        </article>
      )}
    </section>
  );
}
