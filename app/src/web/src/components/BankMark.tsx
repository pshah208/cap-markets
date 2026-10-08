import { useState } from "react";
import { bankInitials, brand, logoSrc } from "../brand";

export function BankMark({ className }: { className: string }) {
  const [failed, setFailed] = useState(false);
  if (logoSrc && !failed) {
    return <img className={className} src={logoSrc} alt={brand.bankName} onError={() => setFailed(true)} />;
  }
  return (
    <span className={`${className} bank-initials`} role="img" aria-label={brand.bankName}>
      {bankInitials(brand.bankShortName)}
    </span>
  );
}
