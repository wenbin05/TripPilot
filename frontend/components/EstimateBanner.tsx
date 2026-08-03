export function EstimateBanner() {
  return (
    <aside className="estimateBanner" aria-label="Important estimate notice">
      <span aria-hidden="true">ⓘ</span>
      <div>
        <strong>Mock data · Proposed trip only</strong>
        <p>
          Prices, hours, and availability are estimates. Nothing has been
          booked. Verify before purchase.
        </p>
      </div>
    </aside>
  );
}
