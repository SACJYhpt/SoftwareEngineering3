import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EditEvent from '../views/EditEvent.vue'
import { ApiError } from '../api'

const { mockRequest, mockRoute, mockRouterPush } = vi.hoisted(() => ({
  mockRequest: vi.fn(),
  mockRoute: { params: { id: '42' }, fullPath: '/manage/events/42/edit' },
  mockRouterPush: vi.fn(),
}))

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    request: (...args) => mockRequest(...args),
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: mockRouterPush }),
}))

const EVENT_TYPES = [{ id: 1, name: '參訪' }]
const ACTIVE_DEPARTMENTS = [{ id: 10, name: '資訊工程學系' }]
const ACTIVE_OFFICES = [{ id: 20, name: '學務處' }]

function makeExistingEvent(overrides = {}) {
  return {
    id: 42,
    unit_id: 10,
    unit: { id: 10, name: '資訊工程學系' },
    name: '資工系企業參訪',
    type: '參訪',
    description: '原有描述',
    location: '資工系館',
    contact_information: 'cs@ntou.edu.tw',
    start_time: '2030-05-12T02:00:00Z',
    end_time: '2030-05-12T04:00:00Z',
    registration_start: '2030-05-01T01:00:00Z',
    registration_deadline: '2030-05-09T10:00:00Z',
    capacity: 40,
    status: '開放中',
    notes: null,
    waitlist_enabled: true,
    waitlist_capacity: 20,
    eligibility_identities: ['student'],
    eligibility_department_ids: [10, 99],
    eligibility_grades: [3, 4],
    ...overrides,
  }
}

describe('EditEvent.vue full integration flow (C07 + C08 + H1 + M1 + L9)', () => {
  beforeEach(() => {
    mockRequest.mockReset()
    mockRouterPush.mockReset()
  })

  it('loads waitlist/eligibility state, surfaces 409 WAITLIST_BELOW_CURRENT and 422 ELIGIBILITY_UNIT_INVALID, then succeeds after fixing', async () => {
    const waitlistBelowError = new ApiError(
      409,
      'WAITLIST_BELOW_CURRENT',
      '候補上限不可低於現有候補人數；請先處理名單',
      {},
      { code: 'WAITLIST_BELOW_CURRENT', message: '候補上限不可低於現有候補人數；請先處理名單' },
    )
    const inactiveUnitError = new ApiError(
      422,
      'ELIGIBILITY_UNIT_INVALID',
      '資格限制須使用啟用中的系所或行政單位',
      {},
      { code: 'ELIGIBILITY_UNIT_INVALID', message: '資格限制須使用啟用中的系所或行政單位' },
    )

    mockRequest
      .mockResolvedValueOnce(makeExistingEvent())
      .mockResolvedValueOnce(EVENT_TYPES)
      .mockResolvedValueOnce(ACTIVE_DEPARTMENTS)
      .mockResolvedValueOnce(ACTIVE_OFFICES)
      .mockRejectedValueOnce(waitlistBelowError)
      .mockRejectedValueOnce(inactiveUnitError)
      .mockResolvedValueOnce(makeExistingEvent({ eligibility_department_ids: [10] }))

    const wrapper = mount(EditEvent, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    // Initial form state backfills waitlist and eligibility including inactive unit 99.
    expect(wrapper.get('#waitlist-enabled').element.checked).toBe(true)
    expect(wrapper.get('#waitlist-capacity').element.value).toBe('20')
    expect(wrapper.get('input[type="checkbox"][value="10"]').element.checked).toBe(true)
    expect(wrapper.get('input[type="checkbox"][value="99"]').element.checked).toBe(true)
    expect(wrapper.text()).toContain('已停用單位（ID: 99）')

    // Step 1: Uncheck waitlist and submit -> 409 WAITLIST_BELOW_CURRENT must still render next to waitlist_enabled.
    await wrapper.get('#waitlist-enabled').setValue(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('#waitlist-capacity').exists()).toBe(false)
    expect(wrapper.text()).toContain('候補上限不可低於現有候補人數；請先處理名單')

    // Step 2: Re-check waitlist (restores 20), change name while inactive unit 99 is still checked -> 422 ELIGIBILITY_UNIT_INVALID.
    await wrapper.get('#waitlist-enabled').setValue(true)
    expect(wrapper.get('#waitlist-capacity').element.value).toBe('20')
    await wrapper.get('#name').setValue('資工系企業參訪（更新）')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('資格限制須使用啟用中的系所或行政單位')

    // Step 3: Uncheck inactive unit 99 and submit -> PATCH succeeds with clean active eligibility_department_ids.
    await wrapper.get('input[type="checkbox"][value="99"]').setValue(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const [path, options] = mockRequest.mock.calls[6]
    expect(path).toBe('/events/42')
    expect(options.method).toBe('PATCH')
    expect(options.body).toEqual({
      name: '資工系企業參訪（更新）',
      eligibility_department_ids: [10],
    })
    expect(mockRouterPush).toHaveBeenCalledWith('/events/42')
  })

  it('keeps event types selectable even if unit list requests fail (L9)', async () => {
    mockRequest
      .mockResolvedValueOnce(makeExistingEvent({ eligibility_department_ids: [] }))
      .mockResolvedValueOnce(EVENT_TYPES)
      .mockRejectedValueOnce(new Error('單位服務暫時無法使用'))
      .mockResolvedValueOnce(ACTIVE_OFFICES)

    const wrapper = mount(EditEvent, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.find('#type').exists()).toBe(true)
    expect(wrapper.get('#type').element.value).toBe('參訪')
    expect(wrapper.text()).toContain('部分表單選項載入失敗')
  })
})
