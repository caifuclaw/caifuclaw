import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  FileImageOutlined,
  EyeOutlined,
  LinkOutlined,
  MergeCellsOutlined,
  PlusOutlined,
  PictureOutlined,
  ReloadOutlined,
  ScissorOutlined,
  UploadOutlined
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Checkbox,
  ColorPicker,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  Modal,
  Select,
  Segmented,
  Space,
  Spin,
  Tag,
  Tooltip,
  Upload
} from 'antd'
import type { UploadFile, UploadProps } from 'antd'
import {
  downloadAiImage,
  downloadAiImagesZip,
  fetchAiImageBlob,
  processAiImage,
  type AiImageAssetDto,
  type AiImageOperation
} from '@/api/aiImage'
import { listModelSettings, type ModelSettingDto } from '@/api/system'
import './AiImageProcessing.less'
import { canPickSaveDirectory, pickSaveDirectory } from '@/utils/download'

interface AiImageFormValues {
  image_urls?: string
  mask_image_url?: string
  prompt?: string
  model_setting_id?: number
  size?: string
  aspect_ratio?: string
  resolution?: '1K' | '2K' | '4K'
  custom_aspect_width?: number
  custom_aspect_height?: number
  quality?: 'low' | 'medium' | 'high' | 'auto'
  count?: number
  output_format?: 'png' | 'jpeg' | 'webp'
  output_compression?: number | null
  split_mode?: 'long' | 'grid' | 'ai'
  split_instruction?: string
  split_max_height?: number
  split_rows?: number
  split_columns?: number
  merge_layout?: 'horizontal' | 'vertical' | 'grid'
  merge_columns?: number
  merge_cell_width?: number | null
  merge_cell_height?: number | null
  merge_gap?: number
  merge_fit_mode?: 'contain' | 'cover'
}

interface OperationResultState {
  assets: AiImageAssetDto[]
  sourceAssets: AiImageAssetDto[]
  lastOperation: AiImageOperation | null
}

function createOperationRecord<T>(factory: () => T): Record<AiImageOperation, T> {
  return {
    generate: factory(),
    edit: factory(),
    split: factory(),
    merge: factory()
  }
}

const operationOptions: Array<{ value: AiImageOperation; label: string; icon: ReactNode }> = [
  { value: 'generate', label: '文生图', icon: <PictureOutlined /> },
  { value: 'edit', label: '图片修改', icon: <EditOutlined /> },
  { value: 'split', label: '图片拆分', icon: <ScissorOutlined /> },
  { value: 'merge', label: '图片合并', icon: <MergeCellsOutlined /> }
]

const splitModeOptions = [
  { value: 'ai', label: '智能识别' },
  { value: 'long', label: '长图按高度' },
  { value: 'grid', label: '网格等分' }
]

const aspectRatioOptions = [
  { value: '1:1', label: '1:1', width: 30, height: 30 },
  { value: '3:2', label: '3:2', width: 38, height: 26 },
  { value: '2:3', label: '2:3', width: 27, height: 34 },
  { value: '4:3', label: '4:3', width: 38, height: 28 },
  { value: '3:4', label: '3:4', width: 28, height: 36 },
  { value: '16:9', label: '16:9', width: 40, height: 23 },
  { value: '9:16', label: '9:16', width: 24, height: 38 },
  { value: '21:9', label: '21:9', width: 42, height: 18 },
  { value: '9:21', label: '9:21', width: 18, height: 42 },
  { value: 'custom', label: '自定义', width: 36, height: 30 }
]

const resolutionOptions: Array<{ value: '1K' | '2K' | '4K'; label: string }> = [
  { value: '1K', label: '1K' },
  { value: '2K', label: '2K' },
  { value: '4K', label: '4K' }
]

const initialValues: AiImageFormValues = {
  image_urls: '',
  mask_image_url: '',
  size: '1024x1024',
  aspect_ratio: '1:1',
  resolution: '1K',
  custom_aspect_width: 1,
  custom_aspect_height: 1,
  quality: 'medium',
  count: 1,
  output_format: 'png',
  output_compression: null,
  split_mode: 'ai',
  split_max_height: 2048,
  split_rows: 2,
  split_columns: 2,
  merge_layout: 'grid',
  merge_columns: 2,
  merge_cell_width: null,
  merge_cell_height: null,
  merge_gap: 16,
  merge_fit_mode: 'contain'
}

const emptyOperationResult = (): OperationResultState => ({
  assets: [],
  sourceAssets: [],
  lastOperation: null
})

function assetLabel(asset: AiImageAssetDto) {
  return `${asset.width} x ${asset.height} · ${asset.format.toUpperCase()}`
}

function operationLabel(operation: AiImageOperation) {
  return operationOptions.find((item) => item.value === operation)?.label || '图片处理'
}

function isImageGenerationModel(item: ModelSettingDto) {
  return /(image|img|图片|图像|生图)/i.test(`${item.name} ${item.model}`)
}

function imageUrls(value: unknown) {
  return String(value || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

function isHttpUrl(value: string) {
  try {
    const parsed = new URL(value)
    return ['http:', 'https:'].includes(parsed.protocol)
  } catch {
    return false
  }
}

function roundImageDimension(value: number) {
  return Math.max(16, Math.round(value / 16) * 16)
}

function imageSizeForSettings(aspectRatio: string, resolution: AiImageFormValues['resolution'], customWidth = 1, customHeight = 1) {
  const [rawWidth, rawHeight] = aspectRatio === 'custom'
    ? [customWidth, customHeight]
    : aspectRatio.split(':').map(Number)
  const ratioWidth = Number(rawWidth) || 1
  const ratioHeight = Number(rawHeight) || 1
  const targetLongEdge = resolution === '4K' ? 4096 : resolution === '2K' ? 2048 : 1024
  const maxPixels = resolution === '4K' ? 3840 * 2160 : targetLongEdge * targetLongEdge
  const ratio = ratioWidth / ratioHeight
  let width = ratio >= 1 ? targetLongEdge : targetLongEdge * ratio
  let height = ratio >= 1 ? targetLongEdge / ratio : targetLongEdge
  const scale = Math.min(1, Math.sqrt(maxPixels / (width * height)))
  width = roundImageDimension(width * scale)
  height = roundImageDimension(height * scale)
  return `${width}x${height}`
}

function validateNetworkUrlList(urls: string[], maxCount: number) {
  if (!urls.length) return '请输入至少一个图片网络地址'
  if (urls.length > maxCount) return `网络图片最多 ${maxCount} 张`
  const invalidUrl = urls.find((url) => !isHttpUrl(url))
  return invalidUrl ? `网络图片 URL 无效: ${invalidUrl}` : ''
}

function UploadFilePreview({ file, label }: { file: UploadFile; label: string }) {
  const [previewUrl, setPreviewUrl] = useState('')

  useEffect(() => {
    const existingUrl = file.thumbUrl || file.url
    if (existingUrl) {
      setPreviewUrl(existingUrl)
      return
    }

    const originFile = file.originFileObj
    if (!originFile) {
      setPreviewUrl('')
      return
    }

    const objectUrl = URL.createObjectURL(originFile)
    setPreviewUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])

  if (!previewUrl) {
    return <div className="source-images-editor__thumb-empty"><FileImageOutlined />{label}</div>
  }
  return <Image src={previewUrl} alt={label} preview={{ mask: <EyeOutlined /> }} />
}

interface AiImageSourceEditorProps {
  imageFiles: UploadFile[]
  networkUrls: string[]
  maxCount: number
  label: string
  disabled?: boolean
  uploadProps: UploadProps
  replaceUploadProps: (index: number) => UploadProps
  onRemoveFile: (uid: string) => void
  onRemoveNetwork: (index: number) => void
  onEditNetwork: (index: number) => void
  onAddNetwork: () => void
}

function AiImageSourceEditor({
  imageFiles,
  networkUrls,
  maxCount,
  label,
  disabled = false,
  uploadProps,
  replaceUploadProps,
  onRemoveFile,
  onRemoveNetwork,
  onEditNetwork,
  onAddNetwork
}: AiImageSourceEditorProps) {
  const totalCount = imageFiles.length + networkUrls.length
  const canAppendImage = totalCount < maxCount

  return (
    <div className="source-images-editor ai-image-processing__source-editor">
      <Image.PreviewGroup>
        <ul className="source-images-editor__list" aria-label={label}>
          {imageFiles.map((file, index) => {
            const imageLabel = `本地图片${index + 1}`
            return (
              <li className="source-images-editor__item" key={file.uid}>
                <div className="source-images-editor__thumb">
                  <UploadFilePreview file={file} label={imageLabel} />
                </div>
                <div className="source-images-editor__actions">
                  <Upload {...replaceUploadProps(index)}>
                    <Tooltip title="替换本地图片">
                      <Button aria-label={`替换${imageLabel}`} disabled={disabled} icon={<UploadOutlined />} size="small" />
                    </Tooltip>
                  </Upload>
                  <Tooltip title="删除">
                    <Button aria-label={`删除${imageLabel}`} danger disabled={disabled} icon={<DeleteOutlined />} size="small" onClick={() => onRemoveFile(file.uid)} />
                  </Tooltip>
                </div>
              </li>
            )
          })}
          {networkUrls.map((url, index) => {
            const imageLabel = `网络图片${index + 1}`
            return (
              <li className="source-images-editor__item" key={`${url}-${index}`}>
                <div className="source-images-editor__thumb" title={url}>
                  <Image src={url} alt={imageLabel} preview={{ mask: <EyeOutlined /> }} fallback="" />
                  <div className="ai-image-processing__network-badge"><LinkOutlined /> 网络图</div>
                </div>
                <div className="source-images-editor__actions">
                  <Tooltip title="编辑图片链接">
                    <Button aria-label={`编辑${imageLabel}`} disabled={disabled} icon={<EditOutlined />} size="small" onClick={() => onEditNetwork(index)} />
                  </Tooltip>
                  <Tooltip title="删除">
                    <Button aria-label={`删除${imageLabel}`} danger disabled={disabled} icon={<DeleteOutlined />} size="small" onClick={() => onRemoveNetwork(index)} />
                  </Tooltip>
                </div>
              </li>
            )
          })}
          <li className="source-images-editor__item source-images-editor__item--add">
            <Upload {...uploadProps} disabled={disabled || !canAppendImage}>
              <Tooltip title="上传本地图片">
                <Button aria-label="上传本地图片" className="source-images-editor__add-card" disabled={disabled || !canAppendImage} type="dashed">
                  <PlusOutlined />
                  <span>本地图片</span>
                </Button>
              </Tooltip>
            </Upload>
            <div className="source-images-editor__add-actions">
              <Tooltip title="添加网络图片">
                <Button aria-label="添加网络图片" disabled={disabled || !canAppendImage} icon={<PlusOutlined />} size="small" onClick={onAddNetwork}>
                  网络图
                </Button>
              </Tooltip>
            </div>
            <span className="source-images-editor__count">({totalCount}/{maxCount})</span>
          </li>
        </ul>
      </Image.PreviewGroup>
    </div>
  )
}

export function AiImageProcessing() {
  const { message } = App.useApp()
  const [form] = Form.useForm<AiImageFormValues>()
  const [operation, setOperation] = useState<AiImageOperation>('generate')
  const [imageFiles, setImageFiles] = useState<UploadFile[]>([])
  const [maskFiles, setMaskFiles] = useState<UploadFile[]>([])
  const [networkDialogTarget, setNetworkDialogTarget] = useState<'images' | 'mask' | null>(null)
  const [editingNetworkIndex, setEditingNetworkIndex] = useState<number | null>(null)
  const [networkImageDraft, setNetworkImageDraft] = useState('')
  const [networkImageError, setNetworkImageError] = useState('')
  const [modelSettings, setModelSettings] = useState<ModelSettingDto[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [regeneratingKey, setRegeneratingKey] = useState('')
  const [downloadingKey, setDownloadingKey] = useState('')
  const [batchDownloading, setBatchDownloading] = useState(false)
  const [batchDownloadProgress, setBatchDownloadProgress] = useState(0)
  const [selectedAssetKeys, setSelectedAssetKeys] = useState<string[]>([])
  const [background, setBackground] = useState('#ffffff')
  const [operationResults, setOperationResults] = useState<Record<AiImageOperation, OperationResultState>>(
    () => createOperationRecord(emptyOperationResult)
  )
  const formValuesByOperation = useRef<Record<AiImageOperation, AiImageFormValues>>(
    createOperationRecord(() => ({ ...initialValues }))
  )
  const imageFilesByOperation = useRef<Record<AiImageOperation, UploadFile[]>>(
    createOperationRecord(() => [])
  )
  const maskFilesByOperation = useRef<Record<AiImageOperation, UploadFile[]>>(
    createOperationRecord(() => [])
  )
  const backgroundByOperation = useRef<Record<AiImageOperation, string>>(
    createOperationRecord(() => '#ffffff')
  )

  const needsImageModel = operation === 'generate' || operation === 'edit'
  const maxImages = operation === 'split' ? 1 : 8
  const selectedSplitMode = Form.useWatch('split_mode', form) || 'ai'
  const needsVisionModel = operation === 'split' && selectedSplitMode === 'ai'
  const needsAnyModel = needsImageModel || needsVisionModel
  const selectedMergeLayout = Form.useWatch('merge_layout', form) || 'grid'
  const selectedOutputFormat = Form.useWatch('output_format', form) || 'png'
  const selectedAspectRatio = Form.useWatch('aspect_ratio', form) || '1:1'
  const selectedResolution = Form.useWatch('resolution', form) || '1K'
  const watchedImageUrls = Form.useWatch('image_urls', form) || ''
  const watchedMaskImageUrl = Form.useWatch('mask_image_url', form) || ''
  const networkImageUrls = imageUrls(watchedImageUrls)
  const maskNetworkUrls = String(watchedMaskImageUrl).trim() ? [String(watchedMaskImageUrl).trim()] : []
  const currentResult = operationResults[operation]
  const selectedAssets = currentResult.assets.filter((asset) => selectedAssetKeys.includes(asset.oss_object_key))
  const selectedAssetCount = selectedAssets.length
  const allAssetsSelected = currentResult.assets.length > 0 && selectedAssetCount === currentResult.assets.length
  const busy = submitting || Boolean(regeneratingKey) || batchDownloading
  const activeModelSettings = useMemo(
    () => modelSettings.filter((item) => (
      item.enabled
      && item.endpoint_enabled
      && (needsVisionModel ? item.supports_vision : isImageGenerationModel(item))
    )),
    [modelSettings, needsVisionModel]
  )
  const modelOptions = useMemo(
    () => activeModelSettings.map((item) => ({ value: item.id, label: item.name || item.model })),
    [activeModelSettings]
  )
  useEffect(() => {
    let active = true
    setLoadingModels(true)
    listModelSettings({ enabled_only: true })
      .then((items) => {
        if (!active) return
        const available = (items || []).filter((item) => item.endpoint_enabled)
        setModelSettings(available)
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setLoadingModels(false)
      })
    return () => {
      active = false
    }
  }, [form])

  useEffect(() => {
    if (!needsAnyModel || loadingModels) return
    const current = form.getFieldValue('model_setting_id')
    if (!activeModelSettings.some((item) => item.id === current)) {
      form.setFieldValue(
        'model_setting_id',
        activeModelSettings.find((item) => item.is_default)?.id || activeModelSettings[0]?.id
      )
    }
  }, [activeModelSettings, form, loadingModels, needsAnyModel, operation])

  function saveCurrentOperationState() {
    formValuesByOperation.current[operation] = form.getFieldsValue(true)
    imageFilesByOperation.current[operation] = imageFiles
    maskFilesByOperation.current[operation] = maskFiles
    backgroundByOperation.current[operation] = background
  }

  function activateOperation(next: AiImageOperation) {
    setOperation(next)
    form.resetFields()
    form.setFieldsValue(formValuesByOperation.current[next])
    setImageFiles(imageFilesByOperation.current[next])
    setMaskFiles(maskFilesByOperation.current[next])
    setBackground(backgroundByOperation.current[next])
    closeNetworkDialog()
  }

  function changeOperation(next: AiImageOperation) {
    if (next === operation) return
    saveCurrentOperationState()
    setSelectedAssetKeys([])
    activateOperation(next)
  }

  function validateUpload(file: File) {
    const allowed = ['image/png', 'image/jpeg', 'image/webp', 'image/bmp']
    if (!allowed.includes(file.type)) {
      message.warning('仅支持 PNG、JPEG、WebP、BMP 图片')
      return Upload.LIST_IGNORE
    }
    if (file.size > 25 * 1024 * 1024) {
      message.warning('单张图片不能超过 25MB')
      return Upload.LIST_IGNORE
    }
    return false
  }

  function imageUploadProps(replaceIndex?: number): UploadProps {
    return {
      accept: 'image/png,image/jpeg,image/webp,image/bmp',
      showUploadList: false,
      fileList: replaceIndex == null ? imageFiles : [],
      multiple: replaceIndex == null && operation !== 'split',
      maxCount: replaceIndex == null ? maxImages : 1,
      beforeUpload: validateUpload,
      onChange: ({ file, fileList }) => {
        if (replaceIndex != null) {
          setImageFiles((items) => items.map((item, index) => index === replaceIndex ? file : item))
          return
        }
        const currentNetworkCount = imageUrls(form.getFieldValue('image_urls')).length
        setImageFiles(fileList.slice(0, Math.max(0, maxImages - currentNetworkCount)))
      },
      onRemove: (file) => {
        setImageFiles((items) => items.filter((item) => item.uid !== file.uid))
        return true
      }
    }
  }

  const maskUploadProps: UploadProps = {
    accept: 'image/png,image/jpeg,image/webp,image/bmp',
    showUploadList: false,
    fileList: maskFiles,
    maxCount: 1,
    beforeUpload: validateUpload,
    onChange: ({ fileList }) => {
      setMaskFiles(fileList.slice(-1))
      form.setFieldValue('mask_image_url', '')
    },
    onRemove: () => {
      setMaskFiles([])
      return true
    }
  }

  function appendFormValue(payload: FormData, name: string, value: unknown) {
    if (value === undefined || value === null || value === '') return
    payload.append(name, String(value))
  }

  function openNetworkDialog(target: 'images' | 'mask', index: number | null = null) {
    const urls = imageUrls(form.getFieldValue(target === 'images' ? 'image_urls' : 'mask_image_url'))
    setNetworkDialogTarget(target)
    setEditingNetworkIndex(index)
    setNetworkImageDraft(index == null ? '' : urls[index] || '')
    setNetworkImageError('')
  }

  function closeNetworkDialog() {
    setNetworkDialogTarget(null)
    setEditingNetworkIndex(null)
    setNetworkImageDraft('')
    setNetworkImageError('')
  }

  function saveNetworkDialog() {
    const target = networkDialogTarget
    if (!target) return
    const urls = imageUrls(networkImageDraft)
    const targetMaxCount = target === 'mask' ? 1 : maxImages
    const validationError = editingNetworkIndex != null && urls.length !== 1
      ? '编辑时只能保留一个图片网络地址'
      : validateNetworkUrlList(urls, targetMaxCount)
    if (validationError) {
      setNetworkImageError(validationError)
      return
    }

    if (target === 'mask') {
      setMaskFiles([])
      form.setFieldValue('mask_image_url', urls[0])
      closeNetworkDialog()
      return
    }

    const existing = imageUrls(form.getFieldValue('image_urls'))
    const next = editingNetworkIndex == null
      ? [...existing, ...urls]
      : existing.map((url, index) => index === editingNetworkIndex ? urls[0] : url)
    if (imageFiles.length + next.length > maxImages) {
      setNetworkImageError(`本地图片和网络图片合计不能超过 ${maxImages} 张`)
      return
    }
    form.setFieldValue('image_urls', next.join('\n'))
    closeNetworkDialog()
  }

  function removeNetworkImage(index: number) {
    const urls = imageUrls(form.getFieldValue('image_urls'))
    urls.splice(index, 1)
    form.setFieldValue('image_urls', urls.join('\n'))
  }

  function removeMaskNetworkImage() {
    form.setFieldValue('mask_image_url', '')
  }

  async function submit() {
    const requestedOperation = operation
    const values = await form.validateFields()
    const networkUrls = imageUrls(values.image_urls)
    const inputImageCount = imageFiles.length + networkUrls.length
    const networkValidationError = networkUrls.find((url) => !isHttpUrl(url))
    if (networkValidationError) {
      message.warning(`网络图片 URL 无效: ${networkValidationError}`)
      return
    }
    if (values.mask_image_url?.trim() && !isHttpUrl(values.mask_image_url.trim())) {
      message.warning('蒙版 URL 必须是 http(s) 地址')
      return
    }
    if (inputImageCount > 8) {
      message.warning('本地图片和网络图片合计不能超过 8 张')
      return
    }
    if (operation === 'edit' && !inputImageCount) {
      message.warning('请先添加需要修改的图片')
      return
    }
    if (operation === 'split' && inputImageCount !== 1) {
      message.warning('请选择或输入一张需要拆分的图片')
      return
    }
    if (operation === 'merge' && inputImageCount < 2) {
      message.warning('请至少添加两张需要合并的图片')
      return
    }
    if (needsAnyModel && !values.model_setting_id) {
      message.warning(needsVisionModel ? '请选择已启用的理解模型' : '请选择已启用的图片模型')
      return
    }

    const payload = new FormData()
    appendFormValue(payload, 'operation', operation)
    appendFormValue(payload, 'image_urls', networkUrls.join('\n'))
    appendFormValue(payload, 'mask_image_url', values.mask_image_url?.trim() || '')
    appendFormValue(payload, 'prompt', values.prompt || '')
    appendFormValue(payload, 'model_setting_id', values.model_setting_id)
    if (needsImageModel) {
      appendFormValue(payload, 'size', imageSizeForSettings(
        values.aspect_ratio || '1:1',
        values.resolution || '1K',
        values.custom_aspect_width,
        values.custom_aspect_height
      ))
      appendFormValue(payload, 'quality', 'medium')
      appendFormValue(payload, 'count', 1)
      appendFormValue(payload, 'output_format', 'png')
    } else {
      appendFormValue(payload, 'size', values.size)
      appendFormValue(payload, 'quality', values.quality)
      appendFormValue(payload, 'count', values.count)
      appendFormValue(payload, 'output_format', values.output_format)
      appendFormValue(payload, 'output_compression', values.output_compression)
    }
    appendFormValue(payload, 'split_mode', values.split_mode)
    appendFormValue(payload, 'split_instruction', values.split_instruction)
    appendFormValue(payload, 'split_max_height', values.split_max_height)
    appendFormValue(payload, 'split_rows', values.split_rows)
    appendFormValue(payload, 'split_columns', values.split_columns)
    appendFormValue(payload, 'merge_layout', values.merge_layout)
    appendFormValue(payload, 'merge_columns', values.merge_columns)
    appendFormValue(payload, 'merge_cell_width', values.merge_cell_width)
    appendFormValue(payload, 'merge_cell_height', values.merge_cell_height)
    appendFormValue(payload, 'merge_gap', values.merge_gap)
    appendFormValue(payload, 'merge_background', background)
    appendFormValue(payload, 'merge_fit_mode', values.merge_fit_mode)
    imageFiles.forEach((item) => {
      if (item.originFileObj) payload.append('images', item.originFileObj, item.name)
    })
    const mask = maskFiles[0]?.originFileObj
    if (mask) payload.append('mask_image', mask, mask.name)

    setSubmitting(true)
    try {
      const result = await processAiImage(payload)
      setOperationResults((current) => ({
        ...current,
        [requestedOperation]: {
          assets: result.assets || [],
          sourceAssets: result.source_assets || [],
          lastOperation: result.operation
        }
      }))
      setSelectedAssetKeys([])
      message.success(`${operationLabel(result.operation)}完成，图片已保存`)
    } finally {
      setSubmitting(false)
    }
  }

  function resetCurrentOperation() {
    form.resetFields()
    form.setFieldsValue(initialValues)
    setSelectedAssetKeys([])
    setImageFiles([])
    setMaskFiles([])
    closeNetworkDialog()
    setBackground('#ffffff')
    formValuesByOperation.current[operation] = { ...initialValues }
    imageFilesByOperation.current[operation] = []
    maskFilesByOperation.current[operation] = []
    backgroundByOperation.current[operation] = '#ffffff'
  }

  async function regenerateAsset(asset: AiImageAssetDto) {
    if (!needsImageModel) return
    const requestedOperation = operation
    const values = await form.validateFields()
    if (!values.model_setting_id) {
      message.warning('请选择已启用的图片模型')
      return
    }

    const payload = new FormData()
    appendFormValue(payload, 'operation', 'edit')
    appendFormValue(payload, 'image_urls', asset.url)
    appendFormValue(payload, 'prompt', values.prompt || '')
    appendFormValue(payload, 'model_setting_id', values.model_setting_id)
    appendFormValue(payload, 'size', imageSizeForSettings(
      values.aspect_ratio || '1:1',
      values.resolution || '1K',
      values.custom_aspect_width,
      values.custom_aspect_height
    ))
    appendFormValue(payload, 'quality', 'medium')
    appendFormValue(payload, 'count', 1)
    appendFormValue(payload, 'output_format', 'png')

    setRegeneratingKey(asset.oss_object_key)
    try {
      const result = await processAiImage(payload)
      setOperationResults((current) => ({
        ...current,
        [requestedOperation]: {
          assets: result.assets || [],
          sourceAssets: result.source_assets || [],
          lastOperation: requestedOperation
        }
      }))
      setSelectedAssetKeys([])
      message.success('已基于当前图片重新生成')
    } finally {
      setRegeneratingKey('')
    }
  }

  function editAsset(asset: AiImageAssetDto) {
    saveCurrentOperationState()
    formValuesByOperation.current.edit = {
      ...formValuesByOperation.current.edit,
      image_urls: asset.url
    }
    imageFilesByOperation.current.edit = []
    activateOperation('edit')
    message.success('图片已带入图片修改')
  }

  async function downloadAsset(asset: AiImageAssetDto) {
    setDownloadingKey(asset.oss_object_key)
    try {
      await downloadAiImage(asset)
    } finally {
      setDownloadingKey('')
    }
  }

  function toggleAssetSelection(assetKey: string, checked: boolean) {
    setSelectedAssetKeys((current) => {
      if (checked) return current.includes(assetKey) ? current : [...current, assetKey]
      return current.filter((key) => key !== assetKey)
    })
  }

  function toggleAllAssets(checked: boolean) {
    setSelectedAssetKeys(checked ? currentResult.assets.map((asset) => asset.oss_object_key) : [])
  }

  async function downloadSelectedAssets() {
    if (!selectedAssets.length) {
      message.info('请先选择要下载的图片')
      return
    }

    setBatchDownloading(true)
    setBatchDownloadProgress(0)
    try {
      if (canPickSaveDirectory()) {
        const directory = await pickSaveDirectory()
        if (!directory) return
        const usedNames = new Set<string>()
        for (const [index, asset] of selectedAssets.entries()) {
          const blob = await fetchAiImageBlob(asset)
          const originalName = asset.name || `image-${index + 1}.png`
          const extensionIndex = originalName.lastIndexOf('.')
          const stem = extensionIndex > 0 ? originalName.slice(0, extensionIndex) : originalName
          const suffix = extensionIndex > 0 ? originalName.slice(extensionIndex) : ''
          let filename = originalName
          let duplicateIndex = 2
          while (usedNames.has(filename.toLowerCase())) {
            filename = `${stem} (${duplicateIndex})${suffix}`
            duplicateIndex += 1
          }
          usedNames.add(filename.toLowerCase())
          const fileHandle = await directory.getFileHandle(filename, { create: true })
          const writable = await fileHandle.createWritable()
          try {
            await writable.write(blob)
            await writable.close()
          } catch (error) {
            await writable.abort?.()
            throw error
          }
          setBatchDownloadProgress(index + 1)
        }
        message.success(`已保存 ${selectedAssets.length} 张图片`)
      } else {
        await downloadAiImagesZip(selectedAssets)
        message.success(`已下载 ${selectedAssets.length} 张图片（ZIP）`)
      }
      setSelectedAssetKeys([])
    } catch (error) {
      if ((error as DOMException)?.name === 'AbortError') return
      message.error('批量下载失败，请重试')
    } finally {
      setBatchDownloading(false)
      setBatchDownloadProgress(0)
    }
  }

  return (
    <main className="ai-image-processing">
      <div className="ai-image-processing__heading">
        <div>
          <h1>图片处理</h1>
        </div>
        <Tooltip title="清空当前输入">
          <Button aria-label="清空当前输入" icon={<ReloadOutlined />} onClick={resetCurrentOperation} disabled={busy} />
        </Tooltip>
      </div>

      <Segmented<AiImageOperation>
        className="ai-image-processing__mode"
        value={operation}
        disabled={busy}
        options={operationOptions.map((item) => ({ value: item.value, label: <span>{item.icon}{item.label}</span> }))}
        onChange={changeOperation}
      />

      <div className="ai-image-processing__workspace">
        <section className="ai-image-processing__input" aria-label={`${operationLabel(operation)}输入与参数`}>
          <Form form={form} layout="vertical" initialValues={initialValues} className="ai-image-processing__form">
            <Form.Item name="image_urls" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="mask_image_url" hidden>
              <Input />
            </Form.Item>
            <div className="ai-image-processing__form-scroll">
              {needsImageModel ? (
                <>
                  <Form.Item
                    name="model_setting_id"
                    label="图片模型"
                    rules={[{ required: true, message: '请选择图片模型' }]}
                  >
                    <Select loading={loadingModels} options={modelOptions} placeholder="选择已启用模型" />
                  </Form.Item>
                  {!loadingModels && !modelOptions.length ? (
                    <Alert
                      className="ai-image-processing__model-alert"
                      type="warning"
                      showIcon
                      message="未找到可用图片模型配置"
                      description="请在系统设置中配置图片接口和 gpt-image-2 模型。"
                    />
                  ) : null}
                  <Form.Item
                    name="prompt"
                    label={operation === 'generate' ? '图片描述' : '修改要求'}
                    rules={[{ required: true, whitespace: true, message: '请输入图片描述或修改要求' }, { max: 5000, message: '内容不能超过 5000 个字符' }]}
                  >
                    <Input.TextArea
                      autoSize={{ minRows: 4, maxRows: 8 }}
                      placeholder={operation === 'generate' ? '描述主体、场景、构图、光线与风格' : '说明要保留和要修改的内容'}
                    />
                  </Form.Item>
                </>
              ) : null}

              {operation !== 'generate' ? (
                <Form.Item
                  label={operation === 'edit' ? '原图或参考图' : operation === 'split' ? '待拆分图片' : '待合并图片'}
                  required
                >
                  <div className="ai-image-processing__source-picker">
                    <AiImageSourceEditor
                      imageFiles={imageFiles}
                      networkUrls={networkImageUrls}
                      maxCount={maxImages}
                      label={operation === 'edit' ? '原图或参考图' : operation === 'split' ? '待拆分图片' : '待合并图片'}
                      uploadProps={imageUploadProps()}
                      replaceUploadProps={imageUploadProps}
                      onRemoveFile={(uid) => setImageFiles((items) => items.filter((item) => item.uid !== uid))}
                      onRemoveNetwork={removeNetworkImage}
                      onEditNetwork={(index) => openNetworkDialog('images', index)}
                      onAddNetwork={() => openNetworkDialog('images')}
                    />
                  </div>
                </Form.Item>
              ) : null}

              {operation === 'edit' ? (
                <Form.Item label="局部修改蒙版（透明区域）">
                  <div className="ai-image-processing__source-picker ai-image-processing__source-picker--mask">
                    <AiImageSourceEditor
                      imageFiles={maskFiles}
                      networkUrls={maskNetworkUrls}
                      maxCount={1}
                      label="局部修改蒙版"
                      uploadProps={maskUploadProps}
                      replaceUploadProps={() => maskUploadProps}
                      onRemoveFile={(uid) => setMaskFiles((items) => items.filter((item) => item.uid !== uid))}
                      onRemoveNetwork={removeMaskNetworkImage}
                      onEditNetwork={() => openNetworkDialog('mask', 0)}
                      onAddNetwork={() => openNetworkDialog('mask')}
                    />
                  </div>
                </Form.Item>
              ) : null}

              {operation === 'split' ? (
                <>
                  <Form.Item name="split_mode" label="拆分方式">
                    <Segmented
                      className="ai-image-processing__split-mode"
                      options={splitModeOptions}
                      value={selectedSplitMode}
                      onChange={(value) => form.setFieldValue('split_mode', value as AiImageFormValues['split_mode'])}
                    />
                  </Form.Item>
                  {selectedSplitMode === 'long' ? (
                    <Form.Item name="split_max_height" label="每段最大高度" rules={[{ required: true, message: '请输入每段高度' }]}>
                      <InputNumber min={128} max={8192} addonAfter="px" className="ai-image-processing__number" />
                    </Form.Item>
                  ) : selectedSplitMode === 'grid' ? (
                    <div className="ai-image-processing__inline-fields">
                      <Form.Item name="split_rows" label="行数" rules={[{ required: true, message: '请输入行数' }]}>
                        <InputNumber min={1} max={20} className="ai-image-processing__number" />
                      </Form.Item>
                      <Form.Item name="split_columns" label="列数" rules={[{ required: true, message: '请输入列数' }]}>
                        <InputNumber min={1} max={20} className="ai-image-processing__number" />
                      </Form.Item>
                    </div>
                  ) : (
                    <div className="ai-image-processing__advanced">
                      <Form.Item
                        name="model_setting_id"
                        label="理解模型"
                        rules={[{ required: true, message: '请选择理解模型' }]}
                      >
                        <Select loading={loadingModels} options={modelOptions} placeholder="选择支持图片理解的模型" />
                      </Form.Item>
                      {!loadingModels && !modelOptions.length ? (
                        <Alert
                          className="ai-image-processing__model-alert"
                          type="warning"
                          showIcon
                          message="未找到可用理解模型"
                          description="请在系统设置中为支持图片理解的模型启用图片理解。"
                        />
                      ) : null}
                      <Form.Item name="split_instruction" label="补充要求（可选）" rules={[{ max: 1000, message: '补充要求不能超过 1000 个字符' }]}>
                        <Input.TextArea autoSize={{ minRows: 2, maxRows: 5 }} placeholder="例如：标题和对应商品图保留在同一区域" />
                      </Form.Item>
                    </div>
                  )}
                </>
              ) : null}

              {operation === 'merge' ? (
                <>
                  <Form.Item name="merge_layout" label="排列方式">
                    <Segmented options={[{ value: 'horizontal', label: '横向' }, { value: 'vertical', label: '纵向' }, { value: 'grid', label: '网格' }]} />
                  </Form.Item>
                  {selectedMergeLayout === 'grid' ? (
                    <Form.Item name="merge_columns" label="网格列数">
                      <InputNumber min={1} max={20} className="ai-image-processing__number" />
                    </Form.Item>
                  ) : null}
                  <div className="ai-image-processing__inline-fields">
                    <Form.Item name="merge_cell_width" label="单元格宽度">
                      <InputNumber min={1} max={8192} addonAfter="px" placeholder="自动" className="ai-image-processing__number" />
                    </Form.Item>
                    <Form.Item name="merge_cell_height" label="单元格高度">
                      <InputNumber min={1} max={8192} addonAfter="px" placeholder="自动" className="ai-image-processing__number" />
                    </Form.Item>
                  </div>
                  <div className="ai-image-processing__inline-fields ai-image-processing__inline-fields--merge">
                    <Form.Item name="merge_gap" label="图片间距">
                      <InputNumber min={0} max={200} addonAfter="px" className="ai-image-processing__number" />
                    </Form.Item>
                    <Form.Item name="merge_fit_mode" label="图片适配">
                      <Select options={[{ value: 'contain', label: '完整显示' }, { value: 'cover', label: '裁剪填满' }]} />
                    </Form.Item>
                    <Form.Item label="背景色">
                      <ColorPicker value={background} onChange={(_, hex) => setBackground(hex)} showText />
                    </Form.Item>
                  </div>
                </>
              ) : null}

              <div className="ai-image-processing__output-settings">
                {needsImageModel ? (
                  <div className="ai-image-processing__image-output-settings">
                    <div className="ai-image-processing__output-label"><span aria-hidden="true">*</span>尺寸比例</div>
                    <Form.Item name="aspect_ratio" hidden><Input /></Form.Item>
                    <div className="ai-image-processing__ratio-options" role="radiogroup" aria-label="尺寸比例">
                      {aspectRatioOptions.map((option) => (
                        <button
                          type="button"
                          role="radio"
                          aria-checked={selectedAspectRatio === option.value}
                          className={`ai-image-processing__ratio-option${selectedAspectRatio === option.value ? ' is-selected' : ''}`}
                          key={option.value}
                          onClick={() => form.setFieldValue('aspect_ratio', option.value)}
                        >
                          <span className="ai-image-processing__ratio-shape" style={{ width: option.width, height: option.height }} aria-hidden="true" />
                          <span>{option.label}</span>
                        </button>
                      ))}
                    </div>
                    {selectedAspectRatio === 'custom' ? (
                      <div className="ai-image-processing__custom-ratio" aria-label="自定义尺寸比例">
                        <Form.Item name="custom_aspect_width" rules={[{ required: true, min: 1, max: 100, type: 'number', message: '请输入有效宽度' }]}>
                          <InputNumber min={1} max={100} aria-label="自定义比例宽度" />
                        </Form.Item>
                        <span>:</span>
                        <Form.Item name="custom_aspect_height" rules={[{ required: true, min: 1, max: 100, type: 'number', message: '请输入有效高度' }]}>
                          <InputNumber min={1} max={100} aria-label="自定义比例高度" />
                        </Form.Item>
                      </div>
                    ) : null}
                    <div className="ai-image-processing__output-label"><span aria-hidden="true">*</span>图片分辨率</div>
                    <Form.Item name="resolution" hidden><Input /></Form.Item>
                    <Segmented
                      block
                      className="ai-image-processing__resolution"
                      aria-label="图片分辨率"
                      options={resolutionOptions}
                      value={selectedResolution}
                      onChange={(value) => form.setFieldValue('resolution', value as AiImageFormValues['resolution'])}
                    />
                  </div>
                ) : (
                  <>
                    <span>输出设置</span>
                    <div className="ai-image-processing__inline-fields ai-image-processing__inline-fields--output">
                      <Form.Item name="output_format" label="格式">
                        <Select options={[{ value: 'png', label: 'PNG' }, { value: 'jpeg', label: 'JPEG' }, { value: 'webp', label: 'WebP' }]} />
                      </Form.Item>
                      {selectedOutputFormat === 'jpeg' || selectedOutputFormat === 'webp' ? (
                        <Form.Item name="output_compression" label="压缩质量">
                          <InputNumber min={0} max={100} placeholder="默认" className="ai-image-processing__number" />
                        </Form.Item>
                      ) : null}
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="ai-image-processing__actions">
              <Button type="primary" size="large" icon={<FileImageOutlined />} loading={submitting} onClick={() => void submit()}>
                {operation === 'generate' ? '生成图片' : operation === 'edit' ? '开始修改' : operation === 'split' ? (selectedSplitMode === 'ai' ? '智能拆分' : '开始拆分') : '开始合并'}
              </Button>
            </div>
          </Form>
        </section>

        <section className="ai-image-processing__result" aria-labelledby="ai-image-result-title" aria-busy={submitting}>
          <div className="ai-image-processing__section-heading ai-image-processing__section-heading--result">
            <div>
              <span className="ai-image-processing__eyebrow">处理结果</span>
              <h2 id="ai-image-result-title">图片结果</h2>
            </div>
            {currentResult.lastOperation || currentResult.assets.length ? (
              <Space size={12} wrap>
                {currentResult.lastOperation ? <Tag>{operationLabel(currentResult.lastOperation)}</Tag> : null}
                {currentResult.assets.length ? (
                  <Space size={8} wrap className="ai-image-processing__result-tools">
                    <Tag>共 {currentResult.assets.length} 张</Tag>
                    <Checkbox
                      aria-label="全选处理结果"
                      checked={allAssetsSelected}
                      indeterminate={selectedAssetCount > 0 && !allAssetsSelected}
                      disabled={busy}
                      onChange={(event) => toggleAllAssets(event.target.checked)}
                    >
                      全选{selectedAssetCount ? ` (${selectedAssetCount})` : ''}
                    </Checkbox>
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      loading={batchDownloading}
                      disabled={!selectedAssetCount || busy}
                      onClick={() => void downloadSelectedAssets()}
                    >
                      {batchDownloading && batchDownloadProgress ? `保存中 ${batchDownloadProgress}/${selectedAssetCount}` : '批量下载'}
                    </Button>
                  </Space>
                ) : null}
              </Space>
            ) : null}
          </div>

          {submitting ? (
            <div className="ai-image-processing__loading">
              <Spin size="large" />
              <span>{operation === 'split' && selectedSplitMode === 'ai' ? '正在识别拼接区域并拆分图片' : '正在处理并保存图片'}</span>
            </div>
          ) : currentResult.assets.length ? (
            <div className="ai-image-processing__asset-grid">
              {currentResult.assets.map((asset) => (
                <article className="ai-image-processing__asset" key={asset.oss_object_key}>
                  <div className="ai-image-processing__asset-preview">
                    <Checkbox
                      className="ai-image-processing__asset-select"
                      aria-label={`选择 ${asset.name}`}
                      checked={selectedAssetKeys.includes(asset.oss_object_key)}
                      disabled={busy}
                      onChange={(event) => toggleAssetSelection(asset.oss_object_key, event.target.checked)}
                    />
                    <Image src={asset.url} alt={asset.name} preview={{ mask: '预览' }} />
                  </div>
                  <div className="ai-image-processing__asset-meta">
                    <div className="ai-image-processing__asset-info">
                      <strong title={asset.name}>{asset.name}</strong>
                      <span>{assetLabel(asset)}</span>
                    </div>
                    <Space size={0} className="ai-image-processing__asset-actions">
                      {needsImageModel ? (
                        <>
                          <Tooltip title="重新生成">
                            <Button
                              aria-label={`基于 ${asset.name} 重新生成`}
                              type="text"
                              icon={<ReloadOutlined />}
                              loading={regeneratingKey === asset.oss_object_key}
                              disabled={busy && regeneratingKey !== asset.oss_object_key}
                              onClick={() => void regenerateAsset(asset)}
                            />
                          </Tooltip>
                          <Tooltip title="修改">
                            <Button
                              aria-label={`修改 ${asset.name}`}
                              type="text"
                              icon={<EditOutlined />}
                              disabled={busy}
                              onClick={() => editAsset(asset)}
                            />
                          </Tooltip>
                        </>
                      ) : null}
                      <Tooltip title="下载图片">
                        <Button
                          aria-label={`下载 ${asset.name}`}
                          type="text"
                          icon={<DownloadOutlined />}
                          loading={downloadingKey === asset.oss_object_key}
                          disabled={busy}
                          onClick={() => void downloadAsset(asset)}
                        />
                      </Tooltip>
                    </Space>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty className="ai-image-processing__empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无处理结果" />
          )}

          {currentResult.sourceAssets.length ? <div className="ai-image-processing__source-count">本次使用 {currentResult.sourceAssets.length} 个输入文件</div> : null}
        </section>
      </div>

      <Modal
        open={networkDialogTarget != null}
        title={networkDialogTarget === 'mask' ? (editingNetworkIndex == null ? '添加网络蒙版' : '编辑网络蒙版') : (editingNetworkIndex == null ? '添加网络图片' : '编辑网络图片')}
        onCancel={closeNetworkDialog}
        onOk={saveNetworkDialog}
        okText="确定"
        cancelText="取消"
        destroyOnClose
      >
        {networkDialogTarget === 'mask' ? (
          <Input
            value={networkImageDraft}
            placeholder="https://..."
            aria-label="网络蒙版地址"
            onChange={(event) => {
              setNetworkImageDraft(event.target.value)
              setNetworkImageError('')
            }}
            onPressEnter={saveNetworkDialog}
          />
        ) : (
          <Input.TextArea
            value={networkImageDraft}
            autoSize={{ minRows: 3, maxRows: 7 }}
            placeholder="输入 http(s) 图片地址，每行一个"
            aria-label="网络图片地址"
            onChange={(event) => {
              setNetworkImageDraft(event.target.value)
              setNetworkImageError('')
            }}
          />
        )}
        {networkImageError ? <div className="ai-image-processing__network-error" role="alert">{networkImageError}</div> : null}
        <div className="ai-image-processing__network-hint">
          {networkDialogTarget === 'mask'
            ? '请输入一个 http(s) 蒙版地址。'
            : editingNetworkIndex == null
              ? '支持一次添加多张图片，每行一个 http(s) 地址。'
              : '请输入一个 http(s) 图片地址。'}
        </div>
      </Modal>
    </main>
  )
}
