import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EventForm from '../components/EventForm.vue'
import EventDetail from '../views/EventDetail.vue'
import {
  EVENT_CODE_FIELDS,
  EVENT_FIELDS,
  emptyEventForm,
  eventFormToPayload,
  eventToForm,
} from '../eventForm'

const mockRequest = vi.fn()
const mockRouterPush = vi.fn()
const mockRouterReplace = vi.fn()

vi.mock('../api', () => ({
  request: (...args) => mockRequest(...args),
  download: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '42' }, fullPath: '/events/42' }),
  useRouter: () => ({ push: mockRouterPush, replace: mockRouterReplace }),
}))

function makeValidForm(overrides = {}) {
  return {
    ...emptyEventForm(1),
    name: '企業參訪',
    type: '參訪',
    description: '資工系企業參訪',
    start_time: '2030-05-10T10:00',
    end_time: '2030-05-10T12:00',
    location: '資工系館',
    registration_start: '2030-05-01T09:00',
    registration_deadline: '2030-05-09T18:00',
    contact_information: 'cs@ntou.edu.tw',
    ...overrides,
  }
}

function emptyErrors() {
  return Object.fromEntries(EVENT_FIELDS.map((field) => [field, '']))
}

const DEPARTMENTS = [
  { id: 10, name: '資訊工程學系' },
  { id: 11, name: '電機工程學系' },
]

const OFFICES = [
  { id: 20, name: '學務處' },
]

function mountEventForm(formOverrides = {}, extraProps = {}) {
  const form = reactive(makeValidForm(formOverrides))
  const errors = reactive(emptyErrors())
  const wrapper = mount(EventForm, {
    props: {
      form,
      errors,
      units: [{ id: 10, name: '資訊工程學系' }],
      types: [{ id: 1, name: '參訪' }],
      departments: DEPARTMENTS,
      offices: OFFICES,
      ...extraProps,
    },
  })
  return { wrapper, form, errors }
}

function makeApiEvent(overrides = {}) {
  return {
    id: 42,
    unit_id: 10,
    unit: { id: 10, name: '資訊工程學系' },
    name: '企業參訪',
    type: '參訪',
    description: '資工系企業參訪',
    location: '資工系館',
    contact_information: 'cs@ntou.edu.tw',
    start_time: '2030-05-10T02:00:00Z',
    end_time: '2030-05-10T04:00:00Z',
    registration_start: '2030-05-01T01:00:00Z',
    registration_deadline: '2030-05-09T10:00:00Z',
    capacity: 40,
    registration_count: 5,
    status: '開放中',
    my_registration_status: null,
    can_register: true,
    notes: null,
    waitlist_enabled: false,
    waitlist_capacity: null,
    eligibility_identities: [],
    eligibility_department_ids: [],
    eligibility_grades: [],
    eligibility_description: '不限',
    ...overrides,
  }
}

describe('C08 Eligibility restriction - eventForm.js', () => {
  it('serializes eligibility arrays with strict types (string[] and number[])', () => {
    const payload = eventFormToPayload(makeValidForm({
      eligibility_identities: ['student'],
      eligibility_department_ids: ['10'],
      eligibility_grades: ['4', 3],
    }))
    expect(payload.eligibility_identities).toEqual(['student'])
    expect(payload.eligibility_department_ids).toEqual([10])
    expect(payload.eligibility_department_ids.every((n) => typeof n === 'number')).toBe(true)
    expect(payload.eligibility_grades).toEqual([3, 4])
    expect(payload.eligibility_grades.every((n) => typeof n === 'number')).toBe(true)
  })

  it('restores eligibility arrays in eventToForm and computes minimal PATCH diff', () => {
    const apiEvent = makeApiEvent({
      eligibility_identities: ['student'],
      eligibility_department_ids: [10],
      eligibility_grades: [3, 4],
    })
    const original = eventToForm(apiEvent)
    const form = eventToForm(apiEvent)

    expect(original.eligibility_identities).toEqual(['student'])
    expect(original.eligibility_department_ids).toEqual([10])
    expect(original.eligibility_grades).toEqual([3, 4])

    // Same values in different order should not be treated as changed.
    form.eligibility_grades = [4, 3]
    expect(eventFormToPayload(form, original)).toEqual({})

    // Clearing all restrictions sends empty arrays in PATCH.
    form.eligibility_identities = []
    form.eligibility_department_ids = []
    form.eligibility_grades = []
    expect(eventFormToPayload(form, original)).toEqual({
      eligibility_identities: [],
      eligibility_department_ids: [],
      eligibility_grades: [],
    })
  })

  it('maps ELIGIBILITY_UNIT_INVALID to eligibility_department_ids', () => {
    expect(EVENT_CODE_FIELDS.ELIGIBILITY_UNIT_INVALID).toBe('eligibility_department_ids')
  })
})

describe('C08 Eligibility restriction - EventForm.vue', () => {
  it('allows selecting 資工系 and 3rd/4th grades and produces expected payload', async () => {
    const { wrapper, form } = mountEventForm()

    expect(wrapper.text()).toContain('系所')
    expect(wrapper.text()).toContain('行政單位')
    expect(wrapper.text()).toContain('學務處')

    await wrapper.find('input[type="checkbox"][value="10"]').setValue(true)
    await wrapper.find('input[type="checkbox"][value="3"]').setValue(true)
    await wrapper.find('input[type="checkbox"][value="4"]').setValue(true)

    const payload = eventFormToPayload(form)
    expect(payload.eligibility_identities).toEqual([])
    expect(payload.eligibility_department_ids).toEqual([10])
    expect(payload.eligibility_grades).toEqual([3, 4])
  })

  it('pre-checks existing eligibility selections in edit mode and shows ELIGIBILITY_UNIT_INVALID error', async () => {
    const { wrapper, errors } = mountEventForm(
      {
        eligibility_identities: ['student'],
        eligibility_department_ids: [10],
        eligibility_grades: [3, 4],
      },
      { editing: true },
    )

    expect(wrapper.find('input[type="checkbox"][value="student"]').element.checked).toBe(true)
    expect(wrapper.find('input[type="checkbox"][value="10"]').element.checked).toBe(true)
    expect(wrapper.find('input[type="checkbox"][value="3"]').element.checked).toBe(true)
    expect(wrapper.find('input[type="checkbox"][value="4"]').element.checked).toBe(true)

    errors.eligibility_department_ids = '資格限制須使用啟用中的系所或行政單位'
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('資格限制須使用啟用中的系所或行政單位')
  })

  it('renders inactive unit IDs as removable checkboxes so edit mode is not blocked (H1)', async () => {
    const original = makeValidForm({ eligibility_department_ids: [10, 99] })
    const { wrapper, form } = mountEventForm(
      { eligibility_department_ids: [10, 99] },
      { editing: true },
    )

    expect(wrapper.text()).toContain('已停用單位（ID: 99）')
    const inactiveCheckbox = wrapper.get('input[type="checkbox"][value="99"]')
    expect(inactiveCheckbox.element.checked).toBe(true)

    await inactiveCheckbox.setValue(false)
    expect(form.eligibility_department_ids).toEqual([10])
    expect(wrapper.text()).not.toContain('已停用單位（ID: 99）')
    expect(eventFormToPayload(form, original)).toEqual({
      eligibility_department_ids: [10],
    })
  })
})

describe('C08 Eligibility restriction - EventDetail.vue', () => {
  beforeEach(() => {
    mockRequest.mockReset()
  })

  it('displays formatted grade text labels including graduate grade 5 -> 研究所 1 年級 (M3)', async () => {
    mockRequest.mockResolvedValueOnce(makeApiEvent({
      eligibility_department_ids: [10],
      eligibility_grades: [3, 4, 5],
      eligibility_description: '系所／單位：資訊工程學系；年級：3／4／5',
    }))

    const wrapper = mount(EventDetail, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('報名資格')
    expect(wrapper.text()).toContain('系所／單位：資訊工程學系；年級：大學部 3 年級／大學部 4 年級／研究所 1 年級')
    expect(wrapper.text()).not.toContain('年級：3／4／5')
  })

  it('displays 不限 on EventDetail when no eligibility restrictions are set', async () => {
    mockRequest.mockResolvedValueOnce(makeApiEvent({
      eligibility_description: '不限',
    }))

    const wrapper = mount(EventDetail, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('報名資格')
    const dts = wrapper.findAll('.facts dt')
    const dds = wrapper.findAll('.facts dd')
    const idx = dts.findIndex((dt) => dt.text() === '報名資格')
    expect(idx).toBeGreaterThanOrEqual(0)
    expect(dds[idx].text()).toBe('不限')
  })
})
