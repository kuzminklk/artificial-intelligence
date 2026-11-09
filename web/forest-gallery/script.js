const photos = [
	{
		src: "img/01-light-in-glass-1600.jpg",
		thumb: "img/01-light-in-glass-800.jpg",
		title: "Свет в стекле",
		description: "Блики на стекле и зелень, в которой можно утонуть. Первый кадр задаёт тон всей серии.",
		tag: "Взгляд",
		alt: "Портрет девушки в круглых очках на фоне зелёной листвы",
	},
	{
		src: "img/02-pause-1600.jpg",
		thumb: "img/02-pause-800.jpg",
		title: "Пауза",
		description: "Второй кадр — чуть больше пространства и чуть меньше спешки. Взгляд, в котором слышно тишину.",
		tag: "Тишина",
		alt: "Портрет девушки в очках и сером свитшоте с нашивкой Community",
	},
	{
		src: "img/03-forest-noon-1600.jpg",
		thumb: "img/03-forest-noon-800.jpg",
		title: "Лесной полдень",
		description:
			"Солнце пробивается сквозь кроны и ложится тёплыми пятнами на траву. Лес на несколько секунд становится студией.",
		tag: "Свет",
		alt: "Мужчина стоит в лесу в пятнах солнечного света",
	},
	{
		src: "img/04-inhale-1600.jpg",
		thumb: "img/04-inhale-800.jpg",
		title: "Вдох",
		description: "Голова вверх, глаза закрыты. Короткая пауза, в которой можно просто дышать.",
		tag: "Лёгкость",
		alt: "Женщина в лесу поднимает голову к свету",
	},
]

const root = document.documentElement
const header = document.querySelector("[data-header]")
const progress = document.querySelector(".scroll-progress")
const menuToggle = document.querySelector(".menu-toggle")
const mobileMenu = document.querySelector("#mobile-menu")
const menuLabel = document.querySelector(".menu-toggle-label")
const pageMain = document.querySelector("main")
const pageFooter = document.querySelector(".site-footer")
const skipLink = document.querySelector(".skip-link")

/* Header state and reading progress */
let scrollTicking = false

function updateScrollUI() {
	const y = window.scrollY
	header?.classList.toggle("is-scrolled", y > 18)

	const max = document.documentElement.scrollHeight - window.innerHeight
	const ratio = max > 0 ? Math.min(1, Math.max(0, y / max)) : 0
	progress?.style.setProperty("--progress", ratio.toFixed(4))
	scrollTicking = false
}

window.addEventListener(
	"scroll",
	() => {
		if (!scrollTicking) {
			scrollTicking = true
			window.requestAnimationFrame(updateScrollUI)
		}
	},
	{ passive: true },
)
window.addEventListener("resize", updateScrollUI, { passive: true })
updateScrollUI()

/* Mobile navigation */
let menuOpen = false

function setMenu(open) {
	if (!mobileMenu || !menuToggle) return
	menuOpen = open

	if (!open && window.innerWidth <= 900) {
		menuToggle.focus({ preventScroll: true })
	}

	mobileMenu.inert = !open
	mobileMenu.classList.toggle("is-open", open)
	mobileMenu.setAttribute("aria-hidden", String(!open))
	menuToggle.setAttribute("aria-expanded", String(open))
	document.body.classList.toggle("menu-open", open)
	if (menuLabel) menuLabel.textContent = open ? "Закрыть" : "Меню"

	if (pageMain) pageMain.inert = open
	if (pageFooter) pageFooter.inert = open
	if (skipLink) skipLink.inert = open

	if (open) {
		window.setTimeout(() => {
			mobileMenu.querySelector("a")?.focus({ preventScroll: true })
		}, 60)
	} else {
		// Wait for the anchor jump, then keep keyboard focus on the visible control.
		window.setTimeout(() => {
			if (window.innerWidth <= 900) menuToggle.focus({ preventScroll: true })
		}, 60)
	}
}

menuToggle?.addEventListener("click", () => setMenu(!menuOpen))

mobileMenu?.querySelectorAll("a").forEach((link) => {
	link.addEventListener("click", () => {
		if (menuOpen) setMenu(false)
	})
})

window.addEventListener("resize", () => {
	if (window.innerWidth > 900 && menuOpen) setMenu(false)
})

document.addEventListener("keydown", (event) => {
	if (event.key === "Escape" && menuOpen) setMenu(false)
})

/* Scroll reveals */
const revealElements = document.querySelectorAll(".reveal")
if ("IntersectionObserver" in window) {
	const revealObserver = new IntersectionObserver(
		(entries, observer) => {
			entries.forEach((entry) => {
				if (!entry.isIntersecting) return
				entry.target.classList.add("in-view")
				observer.unobserve(entry.target)
			})
		},
		{ threshold: 0.12, rootMargin: "0px 0px -6% 0px" },
	)

	revealElements.forEach((element) => revealObserver.observe(element))
} else {
	revealElements.forEach((element) => element.classList.add("in-view"))
}

/* Highlight the current section in the navigation */
const navigationLinks = Array.from(document.querySelectorAll(".desktop-nav a, .mobile-menu nav a"))
const observedSections = ["about", "gallery", "finale"].map((id) => document.getElementById(id)).filter(Boolean)

function setActiveSection(hash) {
	navigationLinks.forEach((link) => {
		const isActive = link.getAttribute("href") === hash
		link.classList.toggle("is-active", isActive)
		if (isActive) link.setAttribute("aria-current", "location")
		else link.removeAttribute("aria-current")
	})
}

if ("IntersectionObserver" in window) {
	const sectionObserver = new IntersectionObserver(
		(entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) setActiveSection(`#${entry.target.id}`)
			})
		},
		{ rootMargin: "-32% 0px -60% 0px", threshold: 0 },
	)

	observedSections.forEach((section) => sectionObserver.observe(section))
}

/* Lightbox */
const lightbox = document.querySelector("#lightbox")
const lightboxImage = document.querySelector("#lightbox-image")
const lightboxNumber = document.querySelector("#lightbox-number")
const lightboxCurrent = document.querySelector("#lightbox-current")
const lightboxTitle = document.querySelector("#lightbox-title")
const lightboxDescription = document.querySelector("#lightbox-description")
const lightboxTag = document.querySelector("#lightbox-tag")
const lightboxStatus = document.querySelector("#lightbox-status")
const closeButton = document.querySelector(".lightbox-close")
const previousButton = document.querySelector(".lightbox-prev")
const nextButton = document.querySelector(".lightbox-next")
const stage = document.querySelector(".lightbox-stage")
const lightboxFigure = document.querySelector(".lightbox-figure")
const thumbs = Array.from(document.querySelectorAll("[data-thumb]"))
const openButtons = Array.from(document.querySelectorAll("[data-index]"))

let currentIndex = 0
let lastFocused = null
const preloaded = new Map()

function pad(index) {
	return String(index + 1).padStart(2, "0")
}

function preload(index) {
	const photo = photos[(index + photos.length) % photos.length]
	if (!photo || preloaded.has(photo.src)) return
	const image = new Image()
	image.sizes = "(max-width: 640px) 92vw, 55vw"
	image.srcset = `${photo.thumb} 800w, ${photo.src} 1600w`
	image.src = photo.src
	preloaded.set(photo.src, image)
}

function renderPhoto(index, announce = true) {
	const photo = photos[index]
	if (!photo) return

	lightboxImage.src = photo.src
	lightboxImage.srcset = `${photo.thumb} 800w, ${photo.src} 1600w`
	lightboxImage.sizes = "(max-width: 640px) 92vw, 55vw"
	lightboxImage.alt = photo.alt
	lightboxNumber.textContent = pad(index)
	lightboxCurrent.textContent = pad(index)
	lightboxTitle.textContent = photo.title
	lightboxDescription.textContent = photo.description
	lightboxTag.textContent = photo.tag

	thumbs.forEach((thumb, thumbIndex) => {
		if (thumbIndex === index) thumb.setAttribute("aria-current", "true")
		else thumb.removeAttribute("aria-current")
	})

	if (announce && lightboxStatus) {
		lightboxStatus.textContent = `Кадр ${index + 1} из ${photos.length}: ${photo.title}`
	}

	preload(index + 1)
	preload(index - 1)
	preload(index + 2)
}

function openLightbox(index, trigger) {
	if (!lightbox || !lightboxImage) return
	lastFocused = trigger || document.activeElement
	currentIndex = (index + photos.length) % photos.length
	renderPhoto(currentIndex)

	if (typeof lightbox.showModal === "function") {
		if (!lightbox.open) lightbox.showModal()
	} else {
		lightbox.setAttribute("open", "")
	}

	root.classList.add("lightbox-open")
	window.requestAnimationFrame(() => closeButton?.focus())
}

function closeLightbox() {
	if (!lightbox?.open) return
	lightbox.close()
}

function goTo(index) {
	currentIndex = (index + photos.length) % photos.length
	renderPhoto(currentIndex)
}

function nextPhoto() {
	goTo(currentIndex + 1)
}

function previousPhoto() {
	goTo(currentIndex - 1)
}

openButtons.forEach((button) => {
	button.addEventListener("click", () => {
		openLightbox(Number(button.dataset.index), button)
	})
})

thumbs.forEach((thumb) => {
	thumb.addEventListener("click", () => goTo(Number(thumb.dataset.thumb)))
})

closeButton?.addEventListener("click", closeLightbox)
nextButton?.addEventListener("click", nextPhoto)
previousButton?.addEventListener("click", previousPhoto)

lightbox?.addEventListener("click", (event) => {
	if (performance.now() < ignoreClickUntil) return
	if (event.target === lightbox || event.target === stage || event.target === lightboxFigure) closeLightbox()
})

lightbox?.addEventListener("keydown", (event) => {
	switch (event.key) {
		case "ArrowRight":
			event.preventDefault()
			nextPhoto()
			break
		case "ArrowLeft":
			event.preventDefault()
			previousPhoto()
			break
		case "Home":
			event.preventDefault()
			goTo(0)
			break
		case "End":
			event.preventDefault()
			goTo(photos.length - 1)
			break
		case "Escape":
			event.preventDefault()
			closeLightbox()
			break
	}
})

lightbox?.addEventListener("close", () => {
	root.classList.remove("lightbox-open")
	lightboxImage?.removeAttribute("src")
	lastFocused?.focus?.()
})

/* Keep keyboard focus inside modal surfaces */
function focusableElements(container) {
	return Array.from(
		container.querySelectorAll("button:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])"),
	).filter((element) => element.getClientRects().length > 0)
}

function trapLightboxFocus(event) {
	const focusable = focusableElements(lightbox)
	if (!focusable.length) return
	const first = focusable[0]
	const last = focusable[focusable.length - 1]
	const active = document.activeElement

	if (event.shiftKey) {
		if (active === first || !lightbox.contains(active)) {
			event.preventDefault()
			last.focus()
		}
	} else if (active === last || !lightbox.contains(active)) {
		event.preventDefault()
		first.focus()
	}
}

function trapMenuFocus(event) {
	const links = Array.from(mobileMenu.querySelectorAll("a")).filter((element) => element.getClientRects().length > 0)
	if (!links.length) return
	const first = menuToggle
	const last = links[links.length - 1]

	if (event.shiftKey && document.activeElement === first) {
		event.preventDefault()
		last.focus()
	} else if (!event.shiftKey && document.activeElement === last) {
		event.preventDefault()
		first.focus()
	}
}

document.addEventListener("keydown", (event) => {
	if (event.key !== "Tab") return
	if (lightbox?.open) trapLightboxFocus(event)
	else if (menuOpen) trapMenuFocus(event)
})

/* Swipe navigation */
let pointerStart = null
let ignoreClickUntil = 0

stage?.addEventListener("pointerdown", (event) => {
	if (event.pointerType === "mouse" && event.button !== 0) return
	pointerStart = { x: event.clientX, y: event.clientY, id: event.pointerId }
})

stage?.addEventListener("pointerup", (event) => {
	if (!pointerStart || pointerStart.id !== event.pointerId) return
	const dx = event.clientX - pointerStart.x
	const dy = event.clientY - pointerStart.y
	pointerStart = null

	if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.2) {
		ignoreClickUntil = performance.now() + 400
		if (dx < 0) nextPhoto()
		else previousPhoto()
	}
})

stage?.addEventListener("pointercancel", () => {
	pointerStart = null
})
