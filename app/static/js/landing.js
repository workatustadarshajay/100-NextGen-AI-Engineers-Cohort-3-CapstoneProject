(() => {
    const story = document.querySelector("[data-story]");
    const canvas = document.querySelector("[data-story-canvas]");

    if (!story || !canvas) {
        return;
    }

    const stage = story.querySelector(".story-stage");
    const nav = document.querySelector(".landing-nav");
    const context = canvas.getContext("2d", { alpha: false });
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const progressLine = document.querySelector("[data-progress-line]");
    const progressCount = document.querySelector("[data-progress-count]");
    const copyBlocks = [...document.querySelectorAll("[data-copy]")];
    const revealBlocks = [...document.querySelectorAll("[data-reveal]")];
    const tiltCards = [...document.querySelectorAll("[data-tilt]")];
    const particles = Array.from({ length: 170 }, (_, index) => {
        const seed = index * 12.9898;
        return {
            x: (Math.sin(seed) * 43758.5453) % 1,
            y: (Math.sin(seed + 17.31) * 24634.6345) % 1,
            size: 0.7 + Math.abs(Math.sin(seed + 4)) * 2.5,
            speed: 0.3 + Math.abs(Math.sin(seed + 8)) * 1.2,
            warm: index % 9 === 0,
        };
    }).map((particle) => ({ ...particle, x: Math.abs(particle.x), y: Math.abs(particle.y) }));

    let width = 0;
    let height = 0;
    let pixelRatio = 1;
    let progress = 0;
    let targetProgress = 0;
    let animationFrame = null;
    let ambientFrame = null;
    let clock = 0;
    let pointerX = 0.5;
    let pointerY = 0.5;

    const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
    const mix = (start, end, amount) => start + (end - start) * amount;
    const smooth = (value) => {
        const amount = clamp(value);
        return amount * amount * (3 - 2 * amount);
    };
    const between = (value, start, end) => smooth((value - start) / (end - start));

    const roundRect = (drawContext, x, y, rectWidth, rectHeight, radius) => {
        const corner = Math.min(radius, rectWidth / 2, rectHeight / 2);
        drawContext.beginPath();
        drawContext.moveTo(x + corner, y);
        drawContext.arcTo(x + rectWidth, y, x + rectWidth, y + rectHeight, corner);
        drawContext.arcTo(x + rectWidth, y + rectHeight, x, y + rectHeight, corner);
        drawContext.arcTo(x, y + rectHeight, x, y, corner);
        drawContext.arcTo(x, y, x + rectWidth, y, corner);
        drawContext.closePath();
    };

    const drawGrid = (opacity, scale = 1) => {
        context.save();
        context.globalAlpha = opacity;
        context.strokeStyle = "#2c7380";
        context.lineWidth = 1;
        const gap = 54 * scale;
        const offset = (progress * 40 + clock * 0.012) % gap;
        for (let x = -gap; x < width + gap; x += gap) {
            context.beginPath();
            context.moveTo(x + offset, 0);
            context.lineTo(x + offset, height);
            context.stroke();
        }
        for (let y = -gap; y < height + gap; y += gap) {
            context.beginPath();
            context.moveTo(0, y + offset * 0.35);
            context.lineTo(width, y + offset * 0.35);
            context.stroke();
        }
        context.restore();
    };

    const drawParticles = (amount) => {
        const synthesis = between(progress, 0.14, 0.5);
        const fade = 1 - between(progress, 0.7, 0.88);
        const centerX = width * 0.5;
        const centerY = height * 0.5;

        context.save();
        context.globalCompositeOperation = "screen";
        particles.forEach((particle, index) => {
            const orbit = (index % 5) * 0.2 + progress * particle.speed * 2.7 + clock * 0.00018 * particle.speed;
            const chaosX = particle.x * width + Math.sin(orbit + particle.y * 8) * width * 0.1;
            const chaosY = particle.y * height + Math.cos(orbit + particle.x * 7) * height * 0.08;
            const streamX = centerX + (particle.x - 0.5) * width * 0.38;
            const streamY = centerY + Math.sin(index * 1.8 + progress * 12 + clock * 0.0008) * height * 0.08;
            const parallaxX = (pointerX - 0.5) * width * (0.025 + synthesis * 0.045);
            const parallaxY = (pointerY - 0.5) * height * (0.02 + synthesis * 0.035);
            const x = mix(chaosX, streamX, synthesis) + parallaxX;
            const y = mix(chaosY, streamY, synthesis) + parallaxY;
            const radius = particle.size * (1 + synthesis * 0.9);
            const glow = context.createRadialGradient(x, y, 0, x, y, radius * 7);
            glow.addColorStop(0, particle.warm ? "rgba(255, 146, 124, .9)" : "rgba(0, 242, 254, .82)");
            glow.addColorStop(1, "rgba(0, 242, 254, 0)");
            context.globalAlpha = fade * 0.78;
            context.fillStyle = glow;
            context.beginPath();
            context.arc(x, y, radius * 7, 0, Math.PI * 2);
            context.fill();
            context.globalAlpha = fade;
            context.fillStyle = particle.warm ? "#ff927c" : index % 4 === 0 ? "#b9ff9b" : "#00f2fe";
            context.beginPath();
            context.arc(x, y, radius, 0, Math.PI * 2);
            context.fill();

            if (index % 14 === 0 && synthesis > 0.05) {
                context.globalAlpha = fade * synthesis * 0.28;
                context.strokeStyle = "#00f2fe";
                context.beginPath();
                context.moveTo(x, y);
                context.lineTo(centerX, centerY);
                context.stroke();
            }
        });
        context.restore();
    };

    const drawPipeline = (amount) => {
        if (amount <= 0) {
            return;
        }
        const centerX = width * 0.5;
        const centerY = height * 0.5;
        const pipelineWidth = Math.min(width * 0.42, 620);
        context.save();
        context.globalAlpha = amount * 0.78;
        context.lineWidth = 1;
        context.strokeStyle = "rgba(0, 242, 254, .5)";
        for (let line = -4; line <= 4; line += 1) {
            context.beginPath();
            context.moveTo(centerX - pipelineWidth, centerY + line * 14);
            context.bezierCurveTo(
                centerX - pipelineWidth * 0.45,
                centerY + line * 20,
                centerX - pipelineWidth * 0.24,
                centerY + line * 4,
                centerX,
                centerY + line * 2,
            );
            context.stroke();
        }
        context.globalAlpha = amount * 0.24;
        context.fillStyle = "#00f2fe";
        context.beginPath();
        context.ellipse(centerX, centerY, pipelineWidth * 0.32, 56, 0, 0, Math.PI * 2);
        context.fill();
        context.restore();
    };

    const drawSignalArcs = (amount) => {
        if (amount <= 0) {
            return;
        }
        const centerX = width * 0.5 + (pointerX - 0.5) * width * 0.04;
        const centerY = height * 0.5 + (pointerY - 0.5) * height * 0.03;
        const baseRadius = Math.min(width, height) * (0.16 + amount * 0.08);
        const cycle = clock * 0.0007;

        context.save();
        context.globalCompositeOperation = "screen";
        for (let ring = 0; ring < 3; ring += 1) {
            const radius = baseRadius + ring * 25;
            const direction = ring % 2 === 0 ? 1 : -1;
            context.globalAlpha = amount * (0.16 - ring * 0.035);
            context.strokeStyle = ring === 1 ? "#b9ff9b" : "#00f2fe";
            context.lineWidth = ring === 1 ? 1.5 : 1;
            context.setLineDash([2, 13 + ring * 5]);
            context.lineDashOffset = -cycle * direction * (18 + ring * 8);
            context.beginPath();
            context.arc(centerX, centerY, radius, cycle * direction + ring, Math.PI * 1.45 + cycle * direction + ring);
            context.stroke();
        }

        const pulseAngle = cycle * 1.5;
        const pulseRadius = baseRadius + 25;
        const pulseX = centerX + Math.cos(pulseAngle) * pulseRadius;
        const pulseY = centerY + Math.sin(pulseAngle) * pulseRadius;
        context.setLineDash([]);
        context.globalAlpha = amount * 0.8;
        context.fillStyle = "#b9ff9b";
        context.shadowColor = "#b9ff9b";
        context.shadowBlur = 13;
        context.beginPath();
        context.arc(pulseX, pulseY, 2.5, 0, Math.PI * 2);
        context.fill();
        context.restore();
    };

    const drawTablet = (amount, fade) => {
        if (amount <= 0 || fade <= 0) {
            return;
        }
        const tabletWidth = Math.min(width * 0.5, 690) * (0.78 + amount * 0.22);
        const tabletHeight = tabletWidth * 0.64;
        const x = (width - tabletWidth) / 2;
        const y = (height - tabletHeight) / 2 + height * 0.015;
        const radius = Math.max(14, tabletWidth * 0.025);
        const screenX = x + tabletWidth * 0.035;
        const screenY = y + tabletHeight * 0.045;
        const screenWidth = tabletWidth * 0.93;
        const screenHeight = tabletHeight * 0.91;

        context.save();
        context.globalAlpha = fade * amount;
        context.shadowColor = "rgba(0, 242, 254, .38)";
        context.shadowBlur = 65;
        context.fillStyle = "rgba(0, 242, 254, .16)";
        roundRect(context, x - 5, y - 5, tabletWidth + 10, tabletHeight + 10, radius + 5);
        context.fill();
        context.shadowBlur = 22;
        context.fillStyle = "#182b3d";
        roundRect(context, x, y, tabletWidth, tabletHeight, radius);
        context.fill();
        context.shadowBlur = 0;
        context.strokeStyle = "rgba(194, 244, 255, .55)";
        context.lineWidth = 1;
        roundRect(context, x, y, tabletWidth, tabletHeight, radius);
        context.stroke();

        const screenGradient = context.createLinearGradient(screenX, screenY, screenX, screenY + screenHeight);
        screenGradient.addColorStop(0, "#102638");
        screenGradient.addColorStop(1, "#09131f");
        context.fillStyle = screenGradient;
        roundRect(context, screenX, screenY, screenWidth, screenHeight, radius * 0.72);
        context.fill();

        context.fillStyle = "rgba(213, 243, 247, .74)";
        context.font = `600 ${Math.max(8, tabletWidth * 0.018)}px Space Grotesk`;
        context.fillText("PATIENT SUMMARY", screenX + screenWidth * 0.07, screenY + screenHeight * 0.13);
        context.fillStyle = "rgba(154, 185, 198, .58)";
        context.font = `${Math.max(7, tabletWidth * 0.011)}px DM Sans`;
        context.fillText("Generated from 24 source pages", screenX + screenWidth * 0.07, screenY + screenHeight * 0.19);

        const contentTop = screenY + screenHeight * 0.27;
        const panelX = screenX + screenWidth * 0.07;
        const panelWidth = screenWidth * 0.56;
        const panelHeight = screenHeight * 0.48;
        context.fillStyle = "rgba(220, 244, 246, .045)";
        roundRect(context, panelX, contentTop, panelWidth, panelHeight, 7);
        context.fill();
        context.strokeStyle = "rgba(160, 215, 225, .15)";
        context.stroke();
        context.fillStyle = "#00f2fe";
        context.fillRect(panelX + 10, contentTop + 12, panelWidth * 0.13, 3);
        context.fillStyle = "rgba(235, 249, 250, .78)";
        context.font = `600 ${Math.max(7, tabletWidth * 0.012)}px DM Sans`;
        context.fillText("Chief complaint & HPI", panelX + 10, contentTop + 33);
        for (let row = 0; row < 4; row += 1) {
            context.fillStyle = row === 2 ? "rgba(0, 242, 254, .74)" : "rgba(171, 202, 211, .45)";
            context.fillRect(panelX + 10, contentTop + 52 + row * 14, panelWidth * (0.78 - row * 0.08), 4);
        }

        const labX = panelX + panelWidth + screenWidth * 0.05;
        const labWidth = screenWidth * 0.25;
        context.fillStyle = "rgba(220, 244, 246, .045)";
        roundRect(context, labX, contentTop, labWidth, panelHeight, 7);
        context.fill();
        context.fillStyle = "rgba(185, 255, 155, .86)";
        context.fillRect(labX + 10, contentTop + 12, labWidth * 0.2, 3);
        context.fillStyle = "rgba(235, 249, 250, .72)";
        context.font = `600 ${Math.max(6, tabletWidth * 0.01)}px DM Sans`;
        context.fillText("LAB ANOMALIES", labX + 10, contentTop + 33);
        for (let row = 0; row < 3; row += 1) {
            context.fillStyle = row === 1 ? "#00f2fe" : "rgba(171, 202, 211, .44)";
            context.fillRect(labX + 10, contentTop + 54 + row * 18, labWidth * (0.5 + row * 0.1), 5);
        }

        context.fillStyle = "rgba(0, 242, 254, .1)";
        roundRect(context, screenX + screenWidth * 0.07, screenY + screenHeight * 0.84, screenWidth * 0.86, screenHeight * 0.07, 5);
        context.fill();
        context.fillStyle = "rgba(225, 243, 246, .52)";
        context.font = `${Math.max(6, tabletWidth * 0.009)}px DM Sans`;
        context.fillText("Ask SynapseMed about this chart...", screenX + screenWidth * 0.1, screenY + screenHeight * 0.885);
        context.restore();
    };

    const drawFinalGrid = (amount) => {
        if (amount <= 0) {
            return;
        }
        context.save();
        context.globalAlpha = amount * 0.7;
        context.strokeStyle = "rgba(0, 242, 254, .38)";
        context.lineWidth = 1;
        const cell = Math.max(44, Math.min(width, height) * 0.09);
        const offset = (progress * cell * 1.5 + clock * 0.018) % cell;
        for (let x = -cell; x < width + cell; x += cell) {
            context.beginPath();
            context.moveTo(x + offset, 0);
            context.lineTo(x + offset, height);
            context.stroke();
        }
        for (let y = -cell; y < height + cell; y += cell) {
            context.beginPath();
            context.moveTo(0, y + offset);
            context.lineTo(width, y + offset);
            context.stroke();
        }
        context.restore();
    };

    const render = (value, timestamp = clock) => {
        if (!context || width === 0 || height === 0) {
            return;
        }
        progress = value;
        clock = timestamp;
        const ambientPulse = 0.5 + Math.sin(clock * 0.0012) * 0.5;
        const background = context.createLinearGradient(0, 0, width, height);
        background.addColorStop(0, "#0a0f1d");
        background.addColorStop(0.52, "#0b1828");
        background.addColorStop(1, "#07101b");
        context.fillStyle = background;
        context.fillRect(0, 0, width, height);

        const glow = context.createRadialGradient(width * 0.5, height * 0.52, 0, width * 0.5, height * 0.52, Math.max(width, height) * 0.7);
        glow.addColorStop(0, `rgba(0, 242, 254, ${0.1 + between(value, 0.2, 0.6) * 0.1 + ambientPulse * 0.025})`);
        glow.addColorStop(0.58, "rgba(0, 242, 254, .025)");
        glow.addColorStop(1, "rgba(10, 15, 29, 0)");
        context.fillStyle = glow;
        context.fillRect(0, 0, width, height);

        drawGrid(0.08 + between(value, 0.75, 1) * 0.13, 1);
        drawParticles(value);
        drawPipeline(between(value, 0.18, 0.47));
        drawSignalArcs(between(value, 0.34, 0.72));
        drawTablet(between(value, 0.27, 0.56), 1 - between(value, 0.73, 0.9));
        drawFinalGrid(between(value, 0.76, 1));
    };

    const updateCopy = (value) => {
        if (reduceMotion.matches) {
            return;
        }
        copyBlocks.forEach((copy) => {
            const start = Number(copy.dataset.start || 0);
            const end = Number(copy.dataset.end || 1);
            const fadeIn = start === 0 ? 1 : between(value, start, Math.min(start + 0.07, end));
            const fadeOut = end >= 0.999 ? 1 : 1 - between(value, Math.max(start, end - 0.11), end);
            const opacity = clamp(fadeIn * fadeOut);
            const lift = (1 - fadeIn) * 20 - (1 - fadeOut) * 18;
            const x = copy.classList.contains("story-side-left") || copy.classList.contains("story-callout-one") ? -20 + lift : 20 - lift;
            copy.style.opacity = String(opacity);
            if (copy.classList.contains("story-hero")) {
                copy.style.transform = `translate3d(0, calc(-50% + ${lift}px), 0)`;
            } else if (copy.classList.contains("story-final")) {
                copy.style.transform = `translate3d(-50%, calc(-50% + ${lift}px), 0)`;
            } else if (copy.classList.contains("story-side-left") || copy.classList.contains("story-callout-one")) {
                copy.style.transform = `translate3d(${x}px, ${copy.classList.contains("story-side-left") ? "-50%" : "0"}, 0)`;
            } else if (copy.classList.contains("story-side-right") || copy.classList.contains("story-callout-two")) {
                copy.style.transform = `translate3d(${-x}px, ${copy.classList.contains("story-side-right") ? "-50%" : "0"}, 0)`;
            } else {
                copy.style.transform = `translate3d(-50%, ${lift}px, 0)`;
            }
        });
        if (progressLine) {
            progressLine.style.transform = `scaleX(${value})`;
        }
        if (progressCount) {
            progressCount.textContent = String(Math.round(value * 100)).padStart(2, "0");
        }
    };

    const resize = () => {
        const bounds = story.querySelector(".story-stage").getBoundingClientRect();
        width = bounds.width;
        height = bounds.height;
        pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.floor(width * pixelRatio);
        canvas.height = Math.floor(height * pixelRatio);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
        render(reduceMotion.matches ? 0.56 : progress, clock);
    };

    const updatePointer = (event) => {
        if (reduceMotion.matches || event.pointerType === "touch") {
            return;
        }
        const bounds = stage.getBoundingClientRect();
        pointerX = clamp((event.clientX - bounds.left) / bounds.width);
        pointerY = clamp((event.clientY - bounds.top) / bounds.height);
        stage.style.setProperty("--pointer-x", `${pointerX * 100}%`);
        stage.style.setProperty("--pointer-y", `${pointerY * 100}%`);
    };

    const resetPointer = () => {
        pointerX = 0.5;
        pointerY = 0.5;
        stage.style.setProperty("--pointer-x", "50%");
        stage.style.setProperty("--pointer-y", "50%");
    };

    const setupReveals = () => {
        revealBlocks.forEach((block, index) => {
            block.style.setProperty("--reveal-delay", `${Math.min(index * 70, 280)}ms`);
        });
        if (reduceMotion.matches || !("IntersectionObserver" in window)) {
            revealBlocks.forEach((block) => block.classList.add("is-visible"));
            return;
        }
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) {
                    return;
                }
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.16, rootMargin: "0px 0px -8% 0px" });
        revealBlocks.forEach((block) => observer.observe(block));
    };

    const setupTilt = () => {
        if (reduceMotion.matches) {
            return;
        }
        tiltCards.forEach((card) => {
            card.addEventListener("pointermove", (event) => {
                if (event.pointerType === "touch") {
                    return;
                }
                const bounds = card.getBoundingClientRect();
                const x = (event.clientX - bounds.left) / bounds.width - 0.5;
                const y = (event.clientY - bounds.top) / bounds.height - 0.5;
                card.style.setProperty("--card-rotate-x", `${y * -5}deg`);
                card.style.setProperty("--card-rotate-y", `${x * 6}deg`);
                card.classList.add("is-tilting");
            });
            card.addEventListener("pointerleave", () => {
                card.style.setProperty("--card-rotate-x", "0deg");
                card.style.setProperty("--card-rotate-y", "0deg");
                card.classList.remove("is-tilting");
            });
        });
    };

    const startAmbient = () => {
        if (reduceMotion.matches || document.hidden || ambientFrame) {
            return;
        }
        ambientFrame = window.requestAnimationFrame((timestamp) => {
            ambientFrame = null;
            render(progress, timestamp);
            startAmbient();
        });
    };

    const readScroll = () => {
        const bounds = story.getBoundingClientRect();
        const scrollDistance = Math.max(1, story.offsetHeight - window.innerHeight);
        targetProgress = clamp(-bounds.top / scrollDistance);
        nav?.classList.toggle("is-scrolled", window.scrollY > 18);
        if (!animationFrame) {
            animationFrame = window.requestAnimationFrame(tick);
        }
    };

    const tick = () => {
        animationFrame = null;
        const difference = targetProgress - progress;
        progress += difference * 0.095;
        if (Math.abs(difference) < 0.0005) {
            progress = targetProgress;
        }
        render(progress, clock);
        updateCopy(progress);
        if (Math.abs(targetProgress - progress) > 0.0005) {
            animationFrame = window.requestAnimationFrame(tick);
        }
    };

    const init = () => {
        document.body.classList.add("motion-ready");
        document.body.classList.toggle("is-reduced-motion", reduceMotion.matches);
        setupReveals();
        setupTilt();
        stage.addEventListener("pointermove", updatePointer, { passive: true });
        stage.addEventListener("pointerleave", resetPointer, { passive: true });
        resize();
        window.addEventListener("resize", resize, { passive: true });
        if (reduceMotion.matches) {
            render(0.56, 0);
            return;
        }
        updateCopy(0);
        readScroll();
        window.addEventListener("scroll", readScroll, { passive: true });
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) {
                if (ambientFrame) {
                    window.cancelAnimationFrame(ambientFrame);
                    ambientFrame = null;
                }
                return;
            }
            startAmbient();
        });
        startAmbient();
        reduceMotion.addEventListener?.("change", () => window.location.reload());
    };

    window.lucide?.createIcons();
    init();
})();
