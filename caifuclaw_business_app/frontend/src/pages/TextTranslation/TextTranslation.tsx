import { useMemo, useState } from 'react'
import {
  ClearOutlined,
  CopyOutlined,
  SendOutlined,
  SwapOutlined,
  TranslationOutlined
} from '@ant-design/icons'
import { App, Button, Empty, Form, Input, Select, Space, Spin, Tag, Tooltip } from 'antd'
import { translateText, type TextTranslationResponse } from '@/api/aiTranslation'
import { useTranslationLanguageOptions } from '@/hooks/useTranslationLanguageOptions'
import { copyTextToClipboard } from '@/utils/clipboard'
import './TextTranslation.less'

interface TextTranslationFormValues {
  source_language?: string
  target_language?: string
  text?: string
}

const initialValues: TextTranslationFormValues = {
  source_language: 'auto',
  target_language: 'en',
  text: ''
}

function languageLabel(value: string, options: Array<{ value: string; label: string }>) {
  if (value === 'auto') return '自动检测（auto）'
  return options.find((item) => item.value === value)?.label || value
}

export function TextTranslation() {
  const { message } = App.useApp()
  const [form] = Form.useForm<TextTranslationFormValues>()
  const { options, loading } = useTranslationLanguageOptions()
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<TextTranslationResponse | null>(null)

  const sourceOptions = useMemo(
    () => [{ value: 'auto', label: '自动检测（auto）' }, ...options],
    [options]
  )
  const targetOptions = options
  const sourceLanguage = Form.useWatch('source_language', form) || 'auto'
  const targetLanguage = Form.useWatch('target_language', form) || 'en'
  const sourceText = Form.useWatch('text', form) || ''
  const trimmedSourceText = String(sourceText || '').trim()
  const canCopyResult = !!result?.translated_text

  async function submit(values: TextTranslationFormValues) {
    const text = String(values.text || '').trim()
    if (!text) {
      message.warning('请输入原文')
      return
    }
    setSubmitting(true)
    try {
      const data = await translateText({
        text,
        source_language: values.source_language || 'auto',
        target_language: values.target_language || 'en'
      })
      setResult(data)
      message.success('翻译完成')
    } finally {
      setSubmitting(false)
    }
  }

  function resetAll() {
    form.resetFields()
    setResult(null)
  }

  function swapLanguages() {
    const source = form.getFieldValue('source_language') || 'auto'
    const target = form.getFieldValue('target_language') || 'en'
    form.setFieldsValue({
      source_language: target,
      target_language: source === 'auto' ? 'zh' : source
    })
  }

  async function copyResult() {
    if (!result?.translated_text) return
    try {
      await copyTextToClipboard(result.translated_text)
      message.success('译文已复制')
    } catch {
      message.error('复制失败')
    }
  }

  return (
    <main className="text-translation">
      <div className="text-translation__heading">
        <div className="text-translation__title">
          <span className="text-translation__title-icon"><TranslationOutlined /></span>
          <h1>文字翻译</h1>
        </div>
        <Tooltip title="清空当前内容">
          <Button aria-label="清空当前内容" icon={<ClearOutlined />} onClick={resetAll} disabled={submitting} />
        </Tooltip>
      </div>

      <div className="text-translation__workspace">
        <section className="text-translation__panel" aria-labelledby="text-translation-input-title">
          <div className="text-translation__panel-head">
            <h2 id="text-translation-input-title">原文</h2>
            <Tag>{trimmedSourceText.length} / 5000</Tag>
          </div>

          <Form
            form={form}
            layout="vertical"
            initialValues={initialValues}
            className="text-translation__form"
            onFinish={(values) => void submit(values)}
          >
            <div className="text-translation__language-row">
              <Form.Item label="源语言" name="source_language" rules={[{ required: true, message: '请选择源语言' }]}>
                <Select
                  showSearch
                  loading={loading}
                  optionFilterProp="label"
                  options={sourceOptions}
                  popupMatchSelectWidth={320}
                />
              </Form.Item>
              <Tooltip title="交换语言">
                <Button
                  className="text-translation__swap"
                  aria-label="交换语言"
                  icon={<SwapOutlined />}
                  onClick={swapLanguages}
                  disabled={submitting}
                />
              </Tooltip>
              <Form.Item label="目标语言" name="target_language" rules={[{ required: true, message: '请选择目标语言' }]}>
                <Select
                  showSearch
                  loading={loading}
                  optionFilterProp="label"
                  options={targetOptions}
                  popupMatchSelectWidth={320}
                />
              </Form.Item>
            </div>

            <Form.Item
              label="翻译文本"
              name="text"
              rules={[
                { required: true, whitespace: true, message: '请输入原文' },
                { max: 5000, message: '原文不能超过 5000 个字符' }
              ]}
            >
              <Input.TextArea
                className="text-translation__textarea"
                autoSize={{ minRows: 14, maxRows: 22 }}
                maxLength={5000}
                placeholder="输入需要翻译的文本"
              />
            </Form.Item>

            <Button
              type="primary"
              size="large"
              htmlType="submit"
              icon={<SendOutlined />}
              loading={submitting}
            >
              开始翻译
            </Button>
          </Form>
        </section>

        <section className="text-translation__panel text-translation__panel--result" aria-labelledby="text-translation-result-title" aria-busy={submitting}>
          <div className="text-translation__panel-head">
            <h2 id="text-translation-result-title">译文</h2>
            <Space size={6} wrap>
              <Tag>{languageLabel(sourceLanguage, sourceOptions)} → {languageLabel(targetLanguage, targetOptions)}</Tag>
              {result?.request_id ? <Tag color="blue">{result.request_id.slice(0, 8)}</Tag> : null}
            </Space>
          </div>

          {submitting ? (
            <div className="text-translation__loading"><Spin size="large" /><span>正在翻译</span></div>
          ) : result?.translated_text ? (
            <div className="text-translation__result-body">
              <Input.TextArea
                className="text-translation__textarea text-translation__textarea--result"
                value={result.translated_text}
                autoSize={{ minRows: 14, maxRows: 22 }}
                readOnly
              />
              <div className="text-translation__result-actions">
                <span>{result.translated_char_count} 字符</span>
                <Button icon={<CopyOutlined />} onClick={copyResult} disabled={!canCopyResult}>
                  复制译文
                </Button>
              </div>
            </div>
          ) : (
            <Empty className="text-translation__empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无译文" />
          )}
        </section>
      </div>
    </main>
  )
}
