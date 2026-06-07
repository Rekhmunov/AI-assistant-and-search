import { ProPaymentStatusModal } from "./ProPaymentStatusModal";
import { useProPaymentReturn } from "../hooks/useProPaymentReturn";

type Props = {
  ready: boolean;
};

export function ProPaymentReturnHandler({ ready }: Props) {
  const { modal, setModal, retryConfirm } = useProPaymentReturn(ready);

  if (!modal.open) return null;

  return (
    <ProPaymentStatusModal
      state={modal}
      onClose={() => setModal({ open: false })}
      onRetry={modal.open && (modal.kind === "error" || modal.kind === "pending") ? retryConfirm : undefined}
    />
  );
}
