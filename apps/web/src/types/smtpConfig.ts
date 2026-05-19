/**
 * TypeScript shapes for the admin SMTP config endpoint.
 *
 * Mirror of apps/api/app/schemas/smtp_config.py. The password is
 * write-only: it is never returned by GET. Reads include
 * ``password_set`` so the UI can render a "password stored" indicator
 * and decide whether the form's password field may be left blank.
 */

export type SmtpEncryption = 'NONE' | 'STARTTLS' | 'SSL_TLS';

export interface SmtpConfigBase {
  host: string;
  port: number;
  encryption: SmtpEncryption;
  username: string;
  from_email: string;
  from_name: string;
}

/** Body for PUT /api/v1/admin/settings/smtp. Omit password to keep the
 *  existing encrypted value untouched. */
export interface SmtpConfigUpdate extends SmtpConfigBase {
  password?: string;
}

/** Inline override for POST /test, used when the admin wants to test
 *  in-flight form values before saving. password is required here. */
export interface SmtpConfigCreate extends SmtpConfigBase {
  password: string;
}

/** Response shape for GET / PUT. The encrypted password is never
 *  exposed; password_set indicates whether one is stored. */
export interface SmtpConfigRead extends SmtpConfigBase {
  id: string;
  last_test_at: string | null;
  last_test_status: 'success' | 'failed' | null;
  last_test_error: string | null;
  updated_at: string;
  password_set: boolean;
}

export interface SmtpTestRequest {
  to_email: string;
  config_override?: SmtpConfigCreate;
}

export interface SmtpTestResponse {
  success: boolean;
  message: string;
  latency_ms: number | null;
}
