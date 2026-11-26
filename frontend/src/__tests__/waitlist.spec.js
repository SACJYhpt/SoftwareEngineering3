import { reactive } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EventForm from '../components/EventForm.vue'
import {
  EVENT_CODE_FIELDS,
  EVENT_FIELDS,
  defaultWaitlistCapacity,
  emptyEventForm,
  eventFormToPayload,
  eventToForm,
  validateEventForm,
} from '../eventForm'

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

function mountEventForm(formOverrides = {}, extraProps = {}) {
  const form = reactive(makeValidForm(formOverrides))
  const errors = reactive(emptyErrors())
  const wrapper = mount(EventForm, {
    props: {
      form,
      errors,
      units: [{ id: 1, name: '資訊工程學系' }],
      types: [{ id: 1, name: '參訪' }],
      ...extraProps,
    },
  })
  return { wrapper, form, errors }
}

describe('C07 Waitlist settings - eventForm.js', () => {
  it('computes default waitlist capacity as half of capacity rounded up', () => {
    expect(defaultWaitlistCapacity(40)).toBe('20')
    expect(defaultWaitlistCapacity('40')).toBe('20')
    expect(defaultWaitlistCapacity(5)).toBe('3')
    expect(defaultWaitlistCapacity(1)).toBe('1')
    expect(defaultWaitlistCapacity('')).toBe('')
    expect(defaultWaitlistCapacity(null)).toBe('')
    expect(defaultWaitlistCapacity(0)).toBe('')
    expect(defaultWaitlistCapacity(-4)).toBe('')
  })

  it('validates waitlist rules against capacity and positive integer constraint', () => {
    const errorsUnlimited = emptyErrors()
    expect(validateEventForm(makeValidForm({ capacity: '', waitlist_enabled: true, waitlist_capacity: '5' }), errorsUnlimited)).toBe(false)
    expect(errorsUnlimited.waitlist_enabled).toBeTruthy()

    const errorsZero = emptyErrors()
    expect(validateEventForm(makeValidForm({ capacity: '40', waitlist_enabled: true, waitlist_capacity: '0' }), errorsZero)).toBe(false)
    expect(errorsZero.waitlist_capacity).toBeTruthy()

    const errorsDecimal = emptyErrors()
    expect(validateEventForm(makeValidForm({ capacity: '40', waitlist_enabled: true, waitlist_capacity: '2.5' }), errorsDecimal)).toBe(false)
    expect(errorsDecimal.waitlist_capacity).toBeTruthy()

    const errorsOk = emptyErrors()
    expect(validateEventForm(makeValidForm({ capacity: '40', waitlist_enabled: true, waitlist_capacity: '10' }), errorsOk)).toBe(true)
    expect(errorsOk.waitlist_enabled).toBe('')
    expect(errorsOk.waitlist_capacity).toBe('')
  })

  it('serializes waitlist_enabled as strict boolean and waitlist_capacity as number or null', () => {
    const enabledPayload = eventFormToPayload(makeValidForm({ capacity: '40', waitlist_enabled: true, waitlist_capacity: '10' }))
    expect(enabledPayload.waitlist_enabled).toBe(true)
    expect(typeof enabledPayload.waitlist_enabled).toBe('boolean')
    expect(enabledPayload.waitlist_capacity).toBe(10)
    expect(typeof enabledPayload.waitlist_capacity).toBe('number')

    const disabledPayload = eventFormToPayload(makeValidForm({ capacity: '', waitlist_enabled: false, waitlist_capacity: '' }))
    expect(disabledPayload.waitlist_enabled).toBe(false)
    expect(disabledPayload.waitlist_capacity).toBeNull()
  })

  it('produces minimal PATCH payload when editing waitlist settings', () => {
    const original = eventToForm({
      unit_id: 1,
      name: '企業參訪',
      type: '參訪',
      description: '資工系企業參訪',
      start_time: '2030-05-10T02:00:00Z',
      end_time: '2030-05-10T04:00:00Z',
      location: '資工系館',
      registration_start: '2030-05-01T01:00:00Z',
      registration_deadline: '2030-05-09T10:00:00Z',
      capacity: 40,
      waitlist_enabled: true,
      waitlist_capacity: 20,
      contact_information: 'cs@ntou.edu.tw',
      notes: null,
    })

    expect(original.waitlist_enabled).toBe(true)
    expect(original.waitlist_capacity).toBe('20')

    const updatedCap = eventFormToPayload({ ...original, waitlist_capacity: '10' }, original)
    expect(updatedCap).toEqual({ waitlist_capacity: 10 })

    const clearedCap = eventFormToPayload({ ...original, capacity: '', waitlist_enabled: false, waitlist_capacity: '' }, original)
    expect(clearedCap).toEqual({ capacity: null, waitlist_enabled: false, waitlist_capacity: null })
  })

  it('maps WAITLIST_BELOW_CURRENT to waitlist_capacity field', () => {
    expect(EVENT_CODE_FIELDS.WAITLIST_BELOW_CURRENT).toBe('waitlist_capacity')
  })
})

describe('C07 Waitlist settings - EventForm.vue', () => {
  it('disables waitlist checkbox when capacity is unlimited (empty)', () => {
    const { wrapper, form } = mountEventForm({ capacity: '' })
    const checkbox = wrapper.get('#waitlist-enabled')
    expect(checkbox.element.disabled).toBe(true)
    expect(form.waitlist_enabled).toBe(false)
    expect(wrapper.find('#waitlist-capacity').exists()).toBe(false)
  })

  it('auto-fills default waitlist capacity for 40 -> 20, 5 -> 3, 1 -> 1', async () => {
    const { wrapper, form } = mountEventForm({ capacity: '40' })
    const checkbox = wrapper.get('#waitlist-enabled')
    expect(checkbox.element.disabled).toBe(false)

    await checkbox.setValue(true)
    expect(form.waitlist_capacity).toBe('20')
    expect(wrapper.get('#waitlist-capacity').element.value).toBe('20')

    await wrapper.get('#capacity').setValue('5')
    expect(form.waitlist_capacity).toBe('3')

    await wrapper.get('#capacity').setValue('1')
    expect(form.waitlist_capacity).toBe('1')
  })

  it('preserves user-customized waitlist capacity when capacity changes', async () => {
    const { wrapper, form } = mountEventForm({ capacity: '40' })
    await wrapper.get('#waitlist-enabled').setValue(true)
    expect(form.waitlist_capacity).toBe('20')

    await wrapper.get('#waitlist-capacity').setValue('10')
    expect(Number(form.waitlist_capacity)).toBe(10)
    expect(wrapper.get('#waitlist-capacity').element.value).toBe('10')

    await wrapper.get('#capacity').setValue('50')
    expect(Number(form.waitlist_capacity)).toBe(10)
    expect(eventFormToPayload(form)).toMatchObject({
      capacity: 50,
      waitlist_enabled: true,
      waitlist_capacity: 10,
    })
  })

  it('disables and clears waitlist when capacity is cleared to unlimited', async () => {
    const { wrapper, form } = mountEventForm({ capacity: '40' })
    await wrapper.get('#waitlist-enabled').setValue(true)
    expect(form.waitlist_capacity).toBe('20')

    await wrapper.get('#capacity').setValue('')
    expect(form.waitlist_enabled).toBe(false)
    expect(form.waitlist_capacity).toBe('')
    expect(wrapper.get('#waitlist-enabled').element.disabled).toBe(true)
    expect(wrapper.find('#waitlist-capacity').exists()).toBe(false)
  })

  it('shows WAITLIST_BELOW_CURRENT field error under waitlist_capacity input', async () => {
    const { wrapper, errors } = mountEventForm(
      { capacity: '40', waitlist_enabled: true, waitlist_capacity: '10' },
      { editing: true },
    )
    errors.waitlist_capacity = '候補上限不可低於現有候補人數；請先處理名單'
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('候補上限不可低於現有候補人數；請先處理名單')
  })
})
