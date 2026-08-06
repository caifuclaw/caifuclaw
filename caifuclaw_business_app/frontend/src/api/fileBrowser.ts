/**
 * Company: 深圳智柠网络科技有限公司
 * Author: mohsen liang
 */

import { post } from './http'

export interface FileBrowserSessionResponse {
  url: string
}

export function createFileBrowserSession(): Promise<FileBrowserSessionResponse> {
  return post<FileBrowserSessionResponse>('/api/v1/filebrowser/session')
}
