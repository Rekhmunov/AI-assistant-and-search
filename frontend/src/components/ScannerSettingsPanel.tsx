import { FileText } from "lucide-react";

export function ScannerSettingsPanel() {
  return (
    <div className="scanner-welcome-panel">
      <div className="scanner-welcome-icon">
        <FileText width={32} height={32} strokeWidth={1.5} />
      </div>
      <h3 className="scanner-welcome-title">Как пользоваться</h3>
      <ol className="scanner-welcome-steps">
        <li>Нажмите <strong>«+»</strong> рядом с полем ввода</li>
        <li>Прикрепите фото документа или сделайте снимок</li>
        <li>Нажмите <strong>Отправить</strong></li>
        <li>Получите готовый PDF для скачивания</li>
      </ol>
      <p className="scanner-welcome-tip">
        💡 Можно прикрепить несколько фото сразу — они станут страницами одного PDF
      </p>
    </div>
  );
}
